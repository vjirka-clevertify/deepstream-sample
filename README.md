# DeepStream Traffic Speed Detection

## Project Overview

This project demonstrates real-time vehicle speed detection using NVIDIA DeepStream and Kafka. The application processes video streams, detects vehicles, calculates their speed, and sends the data to a Kafka topic.

## Prerequisites

- Ubuntu 20.04/22.04
- NVIDIA GPU
- NVIDIA drivers
- Docker & Docker Compose
- Python 3.8+
- DeepStream 6.3

## Installation Steps

# Clone the repository

```bash
git clone https://github.com/vjirka-clevertify/deepstream-sample.git
cd deepstream-sample
```

# Setup environment

```bash
python3 -m venv venv
source venv/bin/activate
```

# Install dependencies

```bash
chmod +x install_dependencies.sh
./install_dependencies.sh
```

# start kafka

```bash
docker-compose up -d
```

# start deepstream

```bash
python3 main.py
```

or

```bash
python3 testing.py
```

# view kafka messages

```bash
docker exec -it kafka kafka-console-consumer.sh --topic vehicle_data --bootstrap-server localhost:9092
```
