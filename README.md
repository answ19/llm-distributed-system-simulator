# LLM-Powered Distributed System Simulator

## Overview
This project implements a discrete-event distributed system simulator using SimPy to evaluate load balancing policies under failure conditions.

## Features
- Multiple servers with failure injection
- Load balancing policies:
  - Random
  - Round Robin
  - Shortest Queue
- Performance metrics:
  - Average latency
  - p50 / p95 latency
  - Throughput
- Experimental evaluation across multiple seeds

## Technologies
- Python
- SimPy
- Matplotlib
- Git

## Results
Shortest Queue policy performs best under failure conditions based on p95 latency evaluation.
