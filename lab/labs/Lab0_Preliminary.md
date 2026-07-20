# Preliminary (Gem5)
The gem5 simulator is a modular platform for computer-system architecture research, encompassing system-level architecture as well as processor microarchitecture.

## Useful Resource
https://www.gem5.org/ \
https://link.springer.com/book/10.1007/978-3-031-01755-1


## Installation (Ubuntu)
Reference: https://www.gem5.org/documentation/general_docs/building

### Dependencies
```bash
sudo apt install build-essential git m4 scons zlib1g zlib1g-dev \
    libprotobuf-dev protobuf-compiler libprotoc-dev libgoogle-perftools-dev \
    python3-dev libboost-all-dev pkg-config
```

### Building
```bash
git clone https://github.com/gem5/gem5
cd gem5
git checkout v23.0.0.1
pip install -r requirements.txt
# scons build/{ISA}/gem5.{variant} -j {threads}
scons build/X86/gem5.opt -j $(nproc)
build/X86/gem5.opt configs/learning_gem5/part1/simple.py
```
- ISA: NULL, ARM, X86, RISCV, etc.
- variant: debug, opt(recommend), fast

- Time to build: 15-30 min
- Building typically needs 6-9 GB of memory (depend on {threads}).
  - If memory is insufficient, try increase swap size (recommended) or reduce {threads}.

# Garnet
An On-Chip Network Model for Diverse Interconnect Systems
- Related Files:
  - src/mem/ruby/network/*
  - src/mem/ruby/network/garnet/*
  - configs/example/garnet_synth_traffic.py
  -
- Garnet Standalone: Network without core/memory/IO

#### Building
```bash
rm -r build
scons build/NULL/gem5.opt PROTOCOL=Garnet_standalone -j $(nproc)
```
