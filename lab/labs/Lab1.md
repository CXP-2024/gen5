# Lab1: Running Synthetic Traffic
In this lab, you will learn the basic mechanism and usage of *Garnet*.

### Task 1: Read the tutorial document and the source code, then run the test command. Change the "GlobalFrequency" to "2GHz", rerun the test command.
```bash
./build/NULL/gem5.opt \
configs/example/garnet_synth_traffic.py \
--network=garnet --num-cpus=64 --num-dirs=64 \
--topology=Mesh_XY --mesh-rows=8 \
--inj-vnet=0 --synthetic=uniform_random \
--sim-cycles=10000 --injectionrate=0.01

echo > network_stats.txt
grep "packets_injected::total" m5out/stats.txt | sed 's/system.ruby.network.packets_injected::total\s*/packets_injected = /' >> network_stats.txt
grep "packets_received::total" m5out/stats.txt | sed 's/system.ruby.network.packets_received::total\s*/packets_received = /' >> network_stats.txt
grep "average_packet_queueing_latency" m5out/stats.txt | sed 's/system.ruby.network.average_packet_queueing_latency\s*/average_packet_queueing_latency = /' >> network_stats.txt
grep "average_packet_network_latency" m5out/stats.txt | sed 's/system.ruby.network.average_packet_network_latency\s*/average_packet_network_latency = /' >> network_stats.txt
grep "average_packet_latency" m5out/stats.txt | sed 's/system.ruby.network.average_packet_latency\s*/average_packet_latency = /' >> network_stats.txt
grep "average_hops" m5out/stats.txt | sed 's/system.ruby.network.average_hops\s*/average_hops = /' >> network_stats.txt
```

### Task 2: Complete the units of statistical variables in "GarnetNetwork.hh/cc". Add new metric to the "network_stats.txt": Reception Rate.
Reception Rate (packets/node/cycle): total_packets_received/num-cpus/sim-cycles.

### Task 3: Answer the questions
- What input parameter options are available for the "garnet_synth_traffic.py"? Briefly describe their usage. Where (in which files) are the default parameters defined? (Tips: use -h option)
- What is the unit of "sim-cycles"? What is the unit of "router-latency" and "link-latency". What is the relationship between Tick and Cycle?
- What is the unit of "injectionrate"?
- Where are the GarnetNetworkInterface and GarnetRouter defined?
- In which module(s), packets are generated and injected to the network? In which module(s), packets are buffered during transmission? In which module(s), the program determines if packets can be sent downstream.

## Submit: A Report (PDF)
