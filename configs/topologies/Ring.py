# Copyright (c) 2026
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met: redistributions of source code must retain the above copyright
# notice, this list of conditions and the following disclaimer;
# redistributions in binary form must reproduce the above copyright
# notice, this list of conditions and the following disclaimer in the
# documentation and/or other materials provided with the distribution;
# neither the name of the copyright holders nor the names of its
# contributors may be used to endorse or promote products derived from
# this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

from m5.objects import *
from m5.params import *

from common import FileSystemConfig
from topologies.BaseTopology import SimpleTopology


class Ring(SimpleTopology):
    description = "Ring"

    def __init__(self, controllers):
        self.nodes = controllers

    def makeTopology(self, options, network, IntLink, ExtLink, Router):
        nodes = self.nodes
        num_routers = options.num_cpus
        assert num_routers == 16, "Lab 3 Ring requires exactly 16 routers"

        link_latency = options.link_latency
        router_latency = options.router_latency
        routers = [
            Router(router_id=i, latency=router_latency)
            for i in range(num_routers)
        ]
        network.routers = routers

        controllers_per_router, remainder = divmod(len(nodes), num_routers)
        network_nodes = nodes[: len(nodes) - remainder]
        remainder_nodes = nodes[len(nodes) - remainder :]

        link_count = 0
        ext_links = []
        for index, node in enumerate(network_nodes):
            controller_level, router_id = divmod(index, num_routers)
            assert controller_level < controllers_per_router
            ext_links.append(
                ExtLink(
                    link_id=link_count,
                    ext_node=node,
                    int_node=routers[router_id],
                    latency=link_latency,
                )
            )
            link_count += 1

        for index, node in enumerate(remainder_nodes):
            assert node.type == "DMA_Controller"
            assert index < remainder
            ext_links.append(
                ExtLink(
                    link_id=link_count,
                    ext_node=node,
                    int_node=routers[0],
                    latency=link_latency,
                )
            )
            link_count += 1
        network.ext_links = ext_links

        int_links = []
        for router_id in range(num_routers):
            clockwise_id = (router_id + 1) % num_routers
            int_links.append(
                IntLink(
                    link_id=link_count,
                    src_node=routers[router_id],
                    dst_node=routers[clockwise_id],
                    src_outport="Clockwise",
                    dst_inport="CounterClockwise",
                    latency=link_latency,
                    weight=1,
                )
            )
            link_count += 1

            counterclockwise_id = (router_id - 1) % num_routers
            int_links.append(
                IntLink(
                    link_id=link_count,
                    src_node=routers[router_id],
                    dst_node=routers[counterclockwise_id],
                    src_outport="CounterClockwise",
                    dst_inport="Clockwise",
                    latency=link_latency,
                    weight=1,
                )
            )
            link_count += 1
        network.int_links = int_links

    def registerTopology(self, options):
        for node_id in range(options.num_cpus):
            FileSystemConfig.register_node(
                [node_id],
                MemorySize(options.mem_size) // options.num_cpus,
                node_id,
            )
