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


class Mesh3D(SimpleTopology):
    description = "Mesh3D"

    def __init__(self, controllers):
        self.nodes = controllers

    def makeTopology(self, options, network, IntLink, ExtLink, Router):
        nodes = self.nodes
        size_x = options.torus_x
        size_y = options.torus_y
        size_z = options.torus_z
        num_routers = options.num_cpus

        assert (
            min(size_x, size_y, size_z) >= 2
        ), "Mesh3D dimensions must all be at least 2"
        assert (
            size_x * size_y * size_z == num_routers
        ), "Mesh3D dimension product must equal --num-cpus"

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

        def router_id(x, y, z):
            return z * size_x * size_y + y * size_x + x

        directions = (
            ("East", "West", 1, 0, 0, 1),
            ("West", "East", -1, 0, 0, 1),
            ("North", "South", 0, 1, 0, 2),
            ("South", "North", 0, -1, 0, 2),
            ("Up", "Down", 0, 0, 1, 3),
            ("Down", "Up", 0, 0, -1, 3),
        )

        int_links = []
        for z in range(size_z):
            for y in range(size_y):
                for x in range(size_x):
                    source = router_id(x, y, z)
                    for outport, inport, dx, dy, dz, weight in directions:
                        dest_x = x + dx
                        dest_y = y + dy
                        dest_z = z + dz
                        if not (
                            0 <= dest_x < size_x
                            and 0 <= dest_y < size_y
                            and 0 <= dest_z < size_z
                        ):
                            continue
                        destination = router_id(dest_x, dest_y, dest_z)
                        int_links.append(
                            IntLink(
                                link_id=link_count,
                                src_node=routers[source],
                                dst_node=routers[destination],
                                src_outport=outport,
                                dst_inport=inport,
                                latency=link_latency,
                                weight=weight,
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
