# Kill-Llama

## Introduction



## Environment Setup

### 1. Clone Repository (on Host)

```shell
git clone https://github.com/zhian66/Kill-Llama
cd Kill-Llama
git checkout marss
git lfs pull
```

### 2. Start Docker Container
```shell
docker run -it -p 5900:5900 -v $(pwd):/Kill-Llama ubuntu:12.04 bash
```

### 3. Setup Ubuntu 12.04 Container
```shell
# Update apt sources (Ubuntu 12.04 EOL)
cat > /etc/apt/sources.list << 'EOF'
deb http://old-releases.ubuntu.com/ubuntu/ precise main restricted universe multiverse
deb http://old-releases.ubuntu.com/ubuntu/ precise-updates main restricted universe multiverse
deb http://old-releases.ubuntu.com/ubuntu/ precise-security main restricted universe multiverse
EOF

apt-get update
apt-get install -y g++ zlib1g-dev libsdl1.2-dev python wget make
```

```shell
# Install scons
cd /tmp
wget http://prdownloads.sourceforge.net/scons/scons-2.5.1.tar.gz
tar xzf scons-2.5.1.tar.gz
cd scons-2.5.1
python setup.py install
```

### 4. Build DRAMSim2
```shell
cd /Kill-Llama/DRAMSim2
make clean
make
```

### 5. Build MARSSx86
```shell
cd /Kill-Llama/marss.dramsim

# Fix script permissions
chmod +x qemu/scripts/*
chmod +x ptlsim/tools/*.py

# Compile (c=4 for quad-core)
/usr/local/bin/scons c=4 config=config/default.conf dramsim=/Kill-Llama/DRAMSim2
```

### 6. Extract VM Image
```shell
cd /Kill-Llama/marss.dramsim
unzip ubuntu_12_04.zip
```

### 7. Run MARSSx86
```shell
cd /Kill-Llama/marss.dramsim
export LD_LIBRARY_PATH=/Kill-Llama/DRAMSim2:$LD_LIBRARY_PATH
./qemu/qemu-system-x86_64 -m 8G -drive file=ubuntu_12_04.qcow2,format=qcow2 -simconfig smart.simconfig -vnc :0 -monitor stdio
```

### 8. Connect to VM
#### VNC
Download [RealVNC](https://www.realvnc.com) and connect to `localhost:5900` Login: `user` / `user`

We will enter the Marssx86 simulator, after that, we can run the benchmark!


## Run Benchmark
In the QEMU monitor (or Guest VM):
```
simconfig -run -stats verify_dram.stats -stopinsns 100000000
```

Results will be saved in results_smart/ directory.

