"""
 values to be used throughout swarm
"""

import os

AuthPath = os.path.expanduser('~/.ssh')
Region = 'ap-southeast-2'
Zone = 'ap-southeast-2a'
Flavour = 't2.micro'
Image = None
Key = 'ec2_sydney'
NamePrefix = 'instance{number}'
Secgroup = 'sydney'
State = 'running'
Userdata = None

