from proxmoxer import ProxmoxAPI, ResourceException
import urllib3
import os
import logging
import time
import argparse

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def verify_all_needed_env_variables_exist():
    mandatory_variables = [
        "PROXMOX_NODE_NAME",
        "PROXMOX_HOST",
        "PROXMOX_LOGIN",
        "PROXMOX_PASSWORD"
    ]
    for variable in mandatory_variables:
        if variable not in os.environ:
            raise Exception(f"{variable} not defined!")

def run_with_timeout(exec_func, verify_func, timeout=120):
    start_time = time.time()
    while time.time() - start_time < timeout:
        res = exec_func()
        if not verify_func():
            logging.info(f"waiting for {verify_func}")
            time.sleep(1)
            continue
        return res
    raise TimeoutError(f"Couldn't verify {verify_func} in {timeout} seconds!")

verify_all_needed_env_variables_exist()

UBUNTU_TEMPLATE_VM_ID = "101"


class Proxmox:
    def __init__(self):
        self.proxmox_node_name = os.getenv("PROXMOX_NODE_NAME")
        self.proxmox_host = os.getenv("PROXMOX_HOST")
        self.proxmox_login = os.getenv("PROXMOX_LOGIN")
        self.proxmox_password = os.getenv("PROXMOX_PASSWORD")
        self._proxmox_api = ProxmoxAPI(
            self.proxmox_host, user=self.proxmox_login, password=self.proxmox_password, verify_ssl=False
        )

    def list_vms(self):
        for vm in self.get_vms():
            print(f"{vm['vmid']}. {vm['name']} => {vm['status']}")

    def get_vms(self):
        return self._proxmox_api.nodes(self.proxmox_node_name).qemu.get()

    def get_existing_ids(self):
        return sorted([vm['vmid'] for vm in self.get_vms()])

    def _generate_new_id(self):
        current_ids = self.get_existing_ids()
        for i in range(110, 200):
            if i not in current_ids:
                return i

    def get_vm_by_id(self, id):
        return self._proxmox_api.nodes(self.proxmox_node_name).qemu(id)

    def get_vm_ip_by_id(self, id):
        vm = self._proxmox_api.nodes(self.proxmox_node_name).qemu(id)
        for interface in vm.agent.get('network-get-interfaces')["result"]:
            if interface["name"] != "lo":
                for ip_address in interface["ip-addresses"]:
                    if ip_address["ip-address-type"] == "ipv4":
                        return ip_address["ip-address"]

    def get_vm_status_by_id(self, id):
        vm = self.get_vm_by_id(id)
        return vm.status().get('current')['qmpstatus']

    def start_vm_by_id(self, id):
        run_with_timeout(
            lambda: self.get_vm_by_id(id).status.post("start"),
            lambda: self.get_vm_status_by_id(id) == "running")

    def wait_for_qemu_agent_response(self, id):
        def verify():
            try:
                ip = self.get_vm_ip_by_id(id)
                return ip is not None
            except ResourceException:
                return False
        run_with_timeout(
            lambda: None,
            verify)

    def shutdown_vm_by_id(self, id):
        run_with_timeout(
            lambda: self.get_vm_by_id(id).status.post("shutdown"),
            lambda: self.get_vm_status_by_id(id) == "stopped")

    def execute_command(self, id, command, no_wait=False):
        vm = self.get_vm_by_id(id)
        logging.info(f"Executing `{command}` on VM id: {id}")
        pid = vm.agent("exec").post(command=command)["pid"]
        if not no_wait:
            status = vm.agent("exec-status").get(pid=pid)
            logging.info(f"Status is: {status}")

    def adjust_hostname(self, id):
        logging.info("Setting hostname")
        self.execute_command(id, f"sed -i \"s/.*/agent-{id}/g\" /etc/hostname")
        logging.info("Rebooting VM to apply hostname")
        self.execute_command(id, "reboot", no_wait=True)
        self.wait_for_qemu_agent_response(id)

    def set_up(self):
        new_id = self._generate_new_id()
        new_name = f"agent-{new_id}"
        qemu_clone = self._proxmox_api.nodes(self.proxmox_node_name).qemu(UBUNTU_TEMPLATE_VM_ID)
        qemu_clone.clone.create(newid=new_id, name=new_name)
        logging.info(f"Created new VM {new_name}")
        logging.info(f"Current status is: {self.get_vm_status_by_id(new_id)}")
        logging.info(f"Starting new VM {new_name}")
        self.start_vm_by_id(new_id)
        logging.info(f"New VM {new_name} started correctly!")
        self.wait_for_qemu_agent_response(new_id)
        self.adjust_hostname(new_id)
        vm_ip = self.get_vm_ip_by_id(new_id)
        logging.info(f"VM {new_id} IP is: {vm_ip}")
        return vm_ip

    def tear_down(self):
        agent_ids = []
        for vm in self.get_vms():
            if vm["name"].startswith("agent"):
                agent_ids.append(vm["vmid"])
        logging.info(f"Going to remove {agent_ids} VMs")
        for id in agent_ids:
            vm = self.get_vm_by_id(id)
            self.shutdown_vm_by_id(id)
            vm.delete()
            logging.info(f"VM {id} deleted successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-t", "--teardown", help="Tear down all agent instances",
                        action="store_true")
    parser.add_argument("-s", "--setup", type=int,
                        help="Specify number of instances to set up")
    parser.add_argument("--silent", help="Silent info messages",
                        action="store_true")
    args = parser.parse_args()

    if args.silent:
        logging.basicConfig(level=logging.WARNING)
    else:
        logging.basicConfig(level=logging.INFO)

    if args.teardown is True and args.setup is not None:
        raise Exception("Not allowed to pass both teardown and setup flags")

    prox = Proxmox()
    if args.setup:
        for i in range(args.setup):
            ip = prox.set_up()
            print(ip)

    if args.teardown:
        prox.tear_down()
