# AWS emergency runbook

This is a clean, parallel AWS run of the v7 experiment. Treat it as a separate dataset from the Mac run. Do not merge Mac and AWS rows in the same final analysis unless Alan explicitly says that is acceptable.

## Recommended setup

Use 8 identical EC2 instances:

- Region: `us-east-1` / N. Virginia
- AMI: Ubuntu Server 24.04 LTS
- Instance type: `c7i.4xlarge` / 16 vCPU / 32 GiB RAM
- Storage: 100 GiB gp3 per instance
- Security group: SSH only from your current IP

Each instance runs PostgreSQL and the Python client locally for one shard of the 960-cell matrix. This is not a Vandevoort-style two-machine DB/client setup; it is the pragmatic deadline setup. It gives a clean AWS-only dataset quickly, while the Mac run continues untouched.

Expected rough time:

- Setup/debug: 1-3 hours the first time
- Experiment runtime: about 3-5 hours with 8 shards, depending on EC2 performance and setup overhead
- EC2 cost: roughly 8 * $0.714/hour = $5.71/hour before storage/tax; a 5-hour run is about $29 plus small storage cost

## Launch and run

On each instance, install git first:

```bash
sudo apt-get update
sudo apt-get install -y git
```

Clone the repo branch:

```bash
git clone --branch v7-experiment https://github.com/ZhangO999/retry-tax-bench.git
cd retry-tax-bench
```

Bootstrap the machine:

```bash
bash scripts/aws_bootstrap_ubuntu.sh
```

Run one shard per instance. For 8 machines, use shard indexes `0` through `7`:

```bash
bash scripts/aws_run_shard.sh 0 8
```

Change the first number on each machine:

```text
machine 1: bash scripts/aws_run_shard.sh 0 8
machine 2: bash scripts/aws_run_shard.sh 1 8
machine 3: bash scripts/aws_run_shard.sh 2 8
machine 4: bash scripts/aws_run_shard.sh 3 8
machine 5: bash scripts/aws_run_shard.sh 4 8
machine 6: bash scripts/aws_run_shard.sh 5 8
machine 7: bash scripts/aws_run_shard.sh 6 8
machine 8: bash scripts/aws_run_shard.sh 7 8
```

Monitor a shard:

```bash
tmux attach -t retry-tax-aws-0-of-8
```

Detach without stopping it:

```text
Ctrl-b then d
```

Tail logs:

```bash
tail -f logs/aws_shard_0_of_8.log
```

## Download results

From your Mac, download each shard directory. Replace the hostnames with the public DNS/IP addresses from EC2:

```bash
mkdir -p /Users/oliverzhang/Desktop/retry-tax-bench/results/aws_v7/shards
rsync -avz -e "ssh -i /path/to/key.pem" ubuntu@EC2_HOST_0:~/retry-tax-bench/results/aws_v7/shards/0 /Users/oliverzhang/Desktop/retry-tax-bench/results/aws_v7/shards/
rsync -avz -e "ssh -i /path/to/key.pem" ubuntu@EC2_HOST_1:~/retry-tax-bench/results/aws_v7/shards/1 /Users/oliverzhang/Desktop/retry-tax-bench/results/aws_v7/shards/
```

Repeat for shards `2` through `7`.

Merge and verify:

```bash
cd /Users/oliverzhang/Desktop/retry-tax-bench
python3 scripts/merge_shard_summaries.py
```

Expected final merged CSV:

```text
results/aws_v7/summary/run_summaries.csv
```

## Stop costs

When all shard files are downloaded, stop or terminate the EC2 instances in the AWS console. Terminate them if you do not need to preserve the disks.
