from checks import AgentCheck

NB = 'virtual-nb.service.strato'
USER = 'admin'
PASSWORD = 'admin'
DOMAIN = 'cloud_admin'
PROJECT = 'default'

def _sumBy(data):
    return sum(d[1] for d in data)

class SympCheck(AgentCheck):
    def check(self, instance):
        import symphony_client
        client = symphony_client.Client(url='http://%s' % NB)
        client.login(domain=DOMAIN, username=USER, password=PASSWORD, project=PROJECT)
        cluster_name = client.nodedapi_cluster.summary()['cluster_name']
        self.report_vms(client, cluster_name)
        self.report_nodes(client, cluster_name)
        self.report_cluster_memory(client, cluster_name)
        self.report_cluster_cpu(client, cluster_name)
        self.report_cluster_storage(client, cluster_name)
        self.report_k8s_clusters(client, cluster_name)
        self.report_rds_instances(client, cluster_name)
        self.report_app_instances(client, cluster_name)
        self.report_cluster_services(client, cluster_name)
        self.report_disks(client, cluster_name)
        self.report_physical_networks(client, cluster_name)

    def report_vms(self, client, cluster_name):
        vms = client.northbound.vms.list()
        self.gauge('cluster.vms.active', '%d' % len([vm for vm in vms if vm['status'] == 'active']), device_name=cluster_name)
        self.gauge('cluster.vms.shutoff', '%d' % len([vm for vm in vms if vm['status'] == 'shutoff']), device_name=cluster_name)
        self.gauge('cluster.vms.error', '%d' % len([vm for vm in vms if vm['status'] == 'error']), device_name=cluster_name)

    def report_nodes(self, client, cluster_name):
        nodes = client.nodes.list()
        self.gauge('cluster.nodes.active', '%d' % len([node for node in nodes if node['state'] == 'active']), device_name=cluster_name)
        self.gauge('cluster.nodes.maintenance', '%d' % len([node for node in nodes if node['state'] == 'in_maintenance']), device_name=cluster_name)
        self.gauge('cluster.nodes.failed', '%d' % len([node for node in nodes if node['state'] == 'failed']), device_name=cluster_name)

    def report_cluster_storage(self, client, cluster_name):
        pools = client.melet.pools.list()
        raw_allocated = raw_capacity = effective_allocated = 0
        for pool in pools:
            raw_allocated = raw_allocated + pool['total_capacity_mb']-pool['free_capacity_mb']
            raw_capacity = raw_capacity + pool['total_capacity_mb']
            effective_allocated = effective_allocated + pool['image_total_mb'] + pool['snapshot_total_mb'] + pool['volume_total_mb']
        self.gauge('cluster.storage.raw_allocated', raw_allocated, device_name=cluster_name)
        self.gauge('cluster.storage.raw_capacity', raw_capacity, device_name=cluster_name)
        self.gauge('cluster.storage.effective_allocated', effective_allocated, device_name=cluster_name)
        
    def report_cluster_memory(self, client, cluster_name):
        mem_raw_capacity = _sumBy(client.metric.query_top('memory__provisioned__of__node__in__MB'))
        mem_raw_free = _sumBy(client.metric.query_top('memory__free__of__node__in__MB'))
        mem_raw_used = _sumBy(client.metric.query_top('memory__used__of__node__in__MB'))
        mem_effective_provisioned = _sumBy(client.metric.query_top('memory__provisioned__of__vm__in__MB'))
        memory_ratio_vms = mem_effective_provisioned / mem_raw_used
        
        self.gauge('cluster.memory.raw_capacity', mem_raw_capacity, device_name=cluster_name)
        self.gauge('cluster.memory.raw_free', mem_raw_free, device_name=cluster_name)
        self.gauge('cluster.memory.raw_used', mem_raw_used, device_name=cluster_name)
        self.gauge('cluster.memory.effective_provisioned', mem_effective_provisioned, device_name=cluster_name)
        self.gauge('cluster.memory.ratio_vms', memory_ratio_vms, device_name=cluster_name)


    def report_cluster_cpu(self, client, cluster_name):
        cpu_count = _sumBy(client.metric.query_top('cpu__count__of__node__in__integer'))
        cpu_raw_provisioned = _sumBy(client.metric.query_top('cpu__provisioned__of__node__in__MHz'))
        cpu_raw_used =_sumBy(client.metric.query_top('cpu__used__of__node__in__MHz'))
        cpu_used_cores = cpu_raw_used / cpu_raw_provisioned * cpu_count
        cpu_effective_allocated = _sumBy(client.metric.query_top('cpu__count__of__vm__in__integer'))
        cpu_ratio = cpu_effective_allocated / cpu_used_cores

        self.gauge('cluster.cpu.allocated', cpu_used_cores, device_name=cluster_name)
        self.gauge('cluster.cpu.free', cpu_count - cpu_used_cores, device_name=cluster_name)
        self.gauge('cluster.cpu.capacity', cpu_count, device_name=cluster_name)
        self.gauge('cluster.cpu.effective_allocated', cpu_effective_allocated, device_name=cluster_name)
        self.gauge('cluster.cpu.ratio', cpu_ratio, device_name=cluster_name)

    def report_k8s_clusters(self, client, cluster_name):
        self.gauge('cluster.services.k8s', '%d' % len(client.kubernetes.clusters.list()), device_name=cluster_name)

    def report_rds_instances(self, client, cluster_name):
        self.gauge('cluster.services.rds', '%d' % len(client.databases.instances.list()), device_name=cluster_name)

    def report_app_instances(self, client, cluster_name):
        self.gauge('cluster.services.apps', '%d' % len(client.apps.instances.list()), device_name=cluster_name)

    def report_cluster_services(self, client, cluster_name):
        failed = 0
        active = 0
        groups = client.nodedapi_cluster.services()
        for services in groups.values():
            for service, nodes_with_statuses in services.iteritems():
                if any(not status for host, status in nodes_with_statuses.iteritems()):
                    failed += 1
                else:
                    active += 1
        self.gauge('cluster.cm.services.active', active, device_name=cluster_name)
        self.gauge('cluster.cm.services.failed', failed, device_name=cluster_name)
    
    def report_disks(self, client, cluster_name):
        disks = client.melet.disks.list()
        disks_num = len(disks)
        healthy_count = 0
        in_use_count = 0
        for disk in disks:
            if disk.health == 'healthy':
                healthy_count += 1
            if disk.state == 'in-use':
                in_use_count += 1
 
        self.gauge('cluster.disks.number', disks_num, device_name=cluster_name)
        self.gauge('cluster.disks.healthy', healthy_count, device_name=cluster_name)
        self.gauge('cluslter.disks.in_use', in_use_count, device_name=cluster_name)

    def report_physical_networks(self, client, cluster_name):
        ifs = client.networking.ethernet_ifs.list()
        self.gauge('cluster.network.ifs_phys.active', '%d' % len([f for f in ifs if f['oper_state'] == 'up']), device_name=cluster_name)
        self.gauge('cluster.network.ifs_phys.inactive', '%d' % len([f for f in ifs if f['oper_state'] != 'up']), device_name=cluster_name)
