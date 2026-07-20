# Lab3: Topology & Flow Control

### Task 1: Implement ring (1D-torus) topology of 16 nodes and a routing algorithm.
- Create "Ring.py" in $gem5/configs/topologies and modify source code in $gem5/src/mem/ruby/network/garnet
- Refer to "Mesh_XY.py" and "RoutingUnit::outportComputeXY()"
- Run ring topology by specifying --topology=Ring
- Invoke custom routing by setting --routing-algorithm=
- Run synthetic traffic, analyze the result

### Task 2: Implement wormhole flow-control.
- It will get enabled when you run Garnet with the option --wormhole
- By default, each VC can only hold one packet. Your wormhole implementation needs to allow it to hold up to 16 single-flit packets.
- Refer to "SwitchAllocator.cc" and "decrement_credit/increment_credit"
- Tips: since we only inject single-flit packets, t_flit->get_type() == HEAD_TAIL_
- Run synthetic traffic, analyze the result. The analysis is supposed to include comparison among:
  - VC = 1, Depth = 1
  - VC = 16, Depth = 1
  - VC = 1, Depth = 16 (i.e., wormhole)

## Submit
- Source code (only modified files)
- A report (PDF)
