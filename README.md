# DeepStream Traffic Speed Detection

## Project Overview
This project demonstrates real-time vehicle speed detection using NVIDIA DeepStream and Kafka. The application processes video streams, detects vehicles, calculates their speed, and sends the data to a Kafka topic.

## Prerequisites
- Ubuntu 20.04/22.04
- NVIDIA GPU
- NVIDIA drivers
- Docker & Docker Compose
- Python 3.8+

## Installation Steps

### 1. Install NVIDIA Components
```bash
# Install NVIDIA drivers
sudo ubuntu-drivers autoinstall
sudo reboot

# Install NVIDIA Container Toolkit
distribution=$(. /etc/os-release;echo $ID$VERSION_ID) \
   && curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add - \
   && curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list

sudo apt-get update
sudo apt-get install -y nvidia-docker2
sudo systemctl restart docker

# Install dependencies
sudo apt install \
    libssl1.1 \
    libgstreamer1.0-0 \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    libgstrtspserver-1.0-0 \
    libjansson4 \
    libyaml-cpp-dev

# Download and install DeepStream
wget https://developer.nvidia.com/deepstream-6.3_6.3.0-1_arm64.deb
sudo apt-get install ./deepstream-6.3_6.3.0-1_arm64.deb

# Setup environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# start kafka
docker-compose up -d

# start deepstream
python main.py

# view kafka messages
docker exec -it kafka kafka-console-consumer.sh --topic vehicle_data --bootstrap-server localhost:9092
```