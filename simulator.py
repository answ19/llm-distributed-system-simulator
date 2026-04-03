import simpy
import random
from dataclasses import dataclass
from typing import List, Callable
import matplotlib.pyplot as plt
import os, csv


@dataclass
class Job:
    job_id: int
    created_at: float
    service_time: float
    done_event: simpy.Event


class Server:
    def __init__(self, env: simpy.Environment, name: str):
        self.env = env
        self.name = name
        self.queue = simpy.Store(env)
        self.is_up = True

        self.busy_time = 0.0
        self.processed = 0

        self.proc = env.process(self.run())

    def run(self):
        while True:
            job: Job = yield self.queue.get()

            while not self.is_up:
                yield self.env.timeout(1.0)

            start = self.env.now
            yield self.env.timeout(job.service_time)
            end = self.env.now

            self.busy_time += (end - start)
            self.processed += 1

            job.done_event.succeed(end)


class LoadBalancer:
    def __init__(self, servers: List[Server], policy: Callable):
        self.servers = servers
        self.policy = policy
        self.rr_index = 0

    def route(self, job: Job):
        state = {
            "servers": [
                {"up": s.is_up, "queue_len": len(s.queue.items)}
                for s in self.servers
            ]
        }

        idx, self.rr_index = self.policy(state, self.rr_index)
        self.servers[idx].queue.put(job)


# -------- POLICIES --------

def policy_random(state, rr_index):
    return random.randrange(len(state["servers"])), rr_index


def policy_round_robin(state, rr_index):
    idx = rr_index % len(state["servers"])
    return idx, (rr_index + 1)


def policy_shortest_queue(state, rr_index):
    best_idx = None
    best_len = float("inf")

    for i, s in enumerate(state["servers"]):
        if s["up"] and s["queue_len"] < best_len:
            best_len = s["queue_len"]
            best_idx = i

    if best_idx is None:
        best_idx = 0

    return best_idx, rr_index


# -------- LLM POLICY --------

def policy_llm(state, rr_index):
    best_idx = None
    best_score = float("inf")

    for i, s in enumerate(state["servers"]):
        if not s["up"]:
            continue

        # smarter scoring
        score = s["queue_len"] * 1.2 + random.uniform(0, 0.3)

        if score < best_score:
            best_score = score
            best_idx = i

    if best_idx is None:
        best_idx = 0

    return best_idx, rr_index


# -------- CLIENT --------

def client(env, client_id, lb, arrival_rate, service_time_fn, metrics, stop_time):
    job_id = 0

    while env.now < stop_time:
        yield env.timeout(random.expovariate(arrival_rate))

        job_id += 1
        done = env.event()

        job = Job(
            job_id=client_id * 1000000 + job_id,
            created_at=env.now,
            service_time=service_time_fn(),
            done_event=done
        )

        lb.route(job)

        finished = yield done
        latency = finished - job.created_at

        metrics["latencies"].append(latency)
        metrics["completed"] += 1


def failure_injector(env, servers, start_at=30, every=40, down_for=15, seed=123):
    rng = random.Random(seed)
    yield env.timeout(start_at)

    while True:
        s = rng.choice(servers)
        s.is_up = False

        yield env.timeout(down_for)

        s.is_up = True
        yield env.timeout(max(0, every - down_for))


# -------- SIMULATION --------

def run_simulation(seed=42, policy_name="round_robin"):
    random.seed(seed)
    env = simpy.Environment()

    servers = [Server(env, f"S{i}") for i in range(3)]
    env.process(failure_injector(env, servers, seed=seed+999))

    policies = {
        "random": policy_random,
        "round_robin": policy_round_robin,
        "shortest_queue": policy_shortest_queue,
        "llm": policy_llm,
    }

    lb = LoadBalancer(servers, policies[policy_name])

    metrics = {"latencies": [], "completed": 0}

    def service_time_fn():
        return max(0.5, random.expovariate(1/3.0))

    for c in range(5):
        env.process(client(env, c, lb, 0.2, service_time_fn, metrics, 200))

    env.run(until=200)

    lat = sorted(metrics["latencies"])

    def pct(p):
        if not lat:
            return None
        return lat[int(p * (len(lat) - 1))]

    return {
        "policy": policy_name,
        "p95_latency": pct(0.95),
        "avg_latency": sum(lat)/len(lat),
        "completed": metrics["completed"],
    }


# -------- MAIN --------

if __name__ == "__main__":
    policies = ["random", "round_robin", "shortest_queue", "llm"]
    seeds = [1, 2, 3, 4, 5]

    all_results = []

    for p in policies:
        for s in seeds:
            all_results.append(run_simulation(seed=s, policy_name=p))

    os.makedirs("results", exist_ok=True)

    with open("results/runs.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=all_results[0].keys())
        writer.writeheader()
        writer.writerows(all_results)

    summary = {}
    for p in policies:
        vals = [r["p95_latency"] for r in all_results if r["policy"] == p]
        summary[p] = sum(vals)/len(vals)

    print("\nAverage p95 latency over seeds:")
    for k, v in summary.items():
        print(f"{k:15s} -> {v:.3f}")

    # Plot
    x = list(summary.keys())
    y = list(summary.values())

    plt.bar(x, y)
    plt.title("Policy Comparison Under Failures")
    plt.ylabel("Average p95 latency")
    plt.xticks(rotation=20)

    os.makedirs("assets", exist_ok=True)
    plt.savefig("assets/p95_bar.png")

    plt.show()
