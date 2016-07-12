#!/bin/bash

swarm stop -p "" -q -y
swarm start -c instance_config -p "example_{number}" -q 2
swarm wait -p example -q ssh
swarm copy -p example -q README.rst "/tmp"
swarm cmd -p example -q "ls -lrt /tmp"
swarm stop -p "" -q -y
