import simpy
import random
from dataclasses import dataclass, field
from typing import List, Callable, Optional
import matplotlib.pyplot as plt
import os, csv

@dataclass
class Job:
    job_id: int
    created_at: float
    service_time: float
    done_event: simpy.Event


class Server:
    """
    A simple server with a single FIFO queue.
    """
    def __init__(self, env: simpy.Environment, name: str):
        self.env = env
        self.name = name
        self.queue = simpy.Store(env)
        self.is_up = True  # later you'll add crashes/recovery

        # Metrics
        self.busy_time = 0.0
        self.processed = 0

        # Start server loop
        self.proc = env.process(self.run())

    def run(self):
        while True:
            job: Job = yield self.queue.get()

            # If server is down, we can either drop or wait.
            # For Week 1: simplest = wait until it comes back up.
            while not self.is_up:
                yield self.env.timeout(1.0)

            start = self.env.now
            yield self.env.timeout(job.service_time)
            end = self.env.now

            self.busy_time += (end - start)
            self.processed += 1

            # Notify client
            job.done_event.succeed(end)

      
class LoadBalancer:
    """
    Routes jobs to servers according to a policy.
    Policy signature:
      policy(state, rr_index) -> (chosen_server_index, new_rr_index)
    """
    def __init__(self, servers: List[Server], policy: Callable):
        self.servers = servers
        self.policy = policy
        self.rr_index = 0  # state for round-robin

    def route(self, job: Job):
        # Build a simple snapshot of the system state for policies (and future LLM)
        state = {
            "time": self.env.now if hasattr(self, "env") else None,
            "servers": [
                {"up": s.is_up, "queue_len": len(s.queue.items)}
                for s in self.servers
            ],
        }
        state = {
            "servers": [{"up": s.is_up, "queue_len": len(s.queue.items)} for s in self.servers]
            }
        idx, self.rr_index = self.policy(state, self.rr_index)

        # IMPORTANT: actually send the job to the chosen server
        self.servers[idx].queue.put(job)

# ---- Policies ----

def policy_random(state, rr_index: int):
    n = len(state["servers"])
    idx = random.randrange(n)
    return idx, rr_index


def policy_round_robin(state, rr_index: int):
    n = len(state["servers"])
    idx = rr_index % n
    rr_index = (rr_index + 1) % n
    return idx, rr_index


def policy_shortest_queue(state, rr_index: int):
    best_idx = None
    best_len = 10**9

    for i, s in enumerate(state["servers"]):
        if s["up"] and s["queue_len"] < best_len:
            best_len = s["queue_len"]
            best_idx = i

    if best_idx is None:
        best_idx = 0

    return best_idx, rr_index

# ---- Client process ----

def client(env: simpy.Environment,
           client_id: int,
           lb: LoadBalancer,
           arrival_rate: float,
           service_time_fn: Callable[[], float],
           metrics: dict,
           stop_time: float):
    """
    Generates jobs until stop_time.
    arrival_rate: lambda for exponential inter-arrival times.
    """
    job_id = 0
    while env.now < stop_time:
        # Time until next job
        interarrival = random.expovariate(arrival_rate)
        yield env.timeout(interarrival)

        job_id += 1
        done = env.event()
        job = Job(
            job_id=client_id * 1_000_000 + job_id,
            created_at=env.now,
            service_time=service_time_fn(),
            done_event=done
        )

        lb.route(job)

        finished_at = yield done
        latency = finished_at - job.created_at
        metrics["latencies"].append(latency)
        metrics["completed"] += 1

def failure_injector(env: simpy.Environment,
                     servers: List[Server],
                     start_at: float = 30.0,
                     every: float = 40.0,
                     down_for: float = 15.0,
                     seed: int = 123):
    """
    Crashes a random server periodically:
      - wait until start_at
      - every 'every' time units: pick a server, mark down, then recover after down_for
    """
    rng = random.Random(seed)
    yield env.timeout(start_at)

    while True:
        s = rng.choice(servers)
        # crash
        s.is_up = False
        # (optional) print events for debugging
        # print(f"[t={env.now:.1f}] {s.name} DOWN")

        yield env.timeout(down_for)

        # recover
        s.is_up = True
        # print(f"[t={env.now:.1f}] {s.name} UP")

        yield env.timeout(max(0.0, every - down_for))

def run_simulation(
    seed: int = 42,
    num_servers: int = 3,
    num_clients: int = 5,
    sim_time: float = 200.0,
    arrival_rate: float = 0.2,   # per client
    policy_name: str = "round_robin",
):
    random.seed(seed)
    env = simpy.Environment()

    servers = [Server(env, f"S{i}") for i in range(num_servers)]
    env.process(failure_injector(env, servers, start_at=30.0, every=40.0, down_for=15.0, seed=seed+999))


    policies = {
        "random": policy_random,
        "round_robin": policy_round_robin,
        "shortest_queue": policy_shortest_queue,
    }
    if policy_name not in policies:
        raise ValueError(f"Unknown policy: {policy_name}")

    lb = LoadBalancer(servers, policies[policy_name])

    metrics = {"latencies": [], "completed": 0}

    # Simple service time distribution
    def service_time_fn():
        # 평균 3.0 time units, min 0.5
        return max(0.5, random.expovariate(1/3.0))

    # Start clients
    for c in range(num_clients):
        env.process(client(env, c, lb, arrival_rate, service_time_fn, metrics, sim_time))

    env.run(until=sim_time)

    # Summary stats
    latencies = metrics["latencies"]
    latencies_sorted = sorted(latencies)
    def percentile(p):
        if not latencies_sorted:
            return None
        k = int(p * (len(latencies_sorted) - 1))
        return latencies_sorted[k]

    results = {
        "policy": policy_name,
        "seed": seed,
        "completed": metrics["completed"],
        "avg_latency": sum(latencies)/len(latencies) if latencies else None,
        "p50_latency": percentile(0.50),
        "p95_latency": percentile(0.95),
        "server_processed": [s.processed for s in servers],
        "server_busy_time": [s.busy_time for s in servers],
        "sim_time": sim_time,
    }
    return results

if __name__ == "__main__":
    policies = ["random", "round_robin", "shortest_queue"]
    seeds = [1, 2, 3, 4, 5]

    all_results = []
    for pol in policies:
        for sd in seeds:
            res = run_simulation(seed=sd, policy_name=pol)
            all_results.append(res)
    
os.makedirs("results", exist_ok=True)
with open("results/runs.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=all_results[0].keys())
    writer.writeheader()
    writer.writerows(all_results)

    print("Saved results to results/runs.csv")
    # Print a simple summary: average p95 latency per policy
    summary = {}
    for pol in policies:
        p95s = [r["p95_latency"] for r in all_results if r["policy"] == pol and r["p95_latency"] is not None]
        summary[pol] = sum(p95s)/len(p95s) if p95s else None

    print("\nAverage p95 latency over seeds:")
    for pol, val in summary.items():
        print(f"  {pol:14s} -> {val:.3f}" if val is not None else f"  {pol:14s} -> None")

    # Plot summary
x = list(summary.keys())
y = [summary[k] for k in x]

plt.figure()
plt.bar(x, y)
plt.ylabel("Average p95 latency")
plt.title("Policy Comparison Under Failures")
plt.xticks(rotation=20)
plt.tight_layout()
os.makedirs("assets", exist_ok=True)

plt.savefig("assets/p95_bar.png", dpi=200)
print("Saved plot to assets/p95_bar.png")

plt.show()

