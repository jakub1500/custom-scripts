#!/bin/bash

set -euo pipefail

usage() { echo "Usage: $0 [-t <target_ip>]" 1>&2; exit 1; }

check_target() {
    echo "PingPonging target to see if it's alive"
    ansible all -i $ANSIBLE_USERNAME@$ip, -m ping
}

get_target_os_release() {
    echo "Checking target's os-release info"
    ansible all -i $ANSIBLE_USERNAME@$ip, -m command --args 'cat /etc/os-release'
}

set_up_k8s() {
    ansible-playbook -i $ANSIBLE_USERNAME@$ip, playbook-prepare-cluster-dependencies.yaml \
        -e containerd_config_cgroup_driver_systemd=true
}

if [[ -z $ANSIBLE_USERNAME ]]; then
    echo "ANSIBLE_USERNAME variable is not set!"
    exit 1
fi

if [[ -z $ANSIBLE_PASSWORD ]]; then
    echo "ANSIBLE_PASSWORD variable is not set!"
    exit 1
fi

ip=""

while getopts ":t:" o; do
    case "${o}" in
        t)
            ip=${OPTARG}
            ;;
        *)
            usage
            ;;
    esac
done

if [[ -z $ip ]]; then
    echo "There is no target selected with -t option!"
    exit 1
fi

check_target
get_target_os_release
set_up_k8s
