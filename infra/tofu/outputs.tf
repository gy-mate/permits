output "master_ipv4" {
  description = "Public IPv4 of the k3s master (SSH here to fetch the kubeconfig)."
  value       = hcloud_server.master.ipv4_address
}

output "master_private_ip" {
  value = "10.0.0.2"
}

output "network_id" {
  description = "Private network id (needed by the cluster-autoscaler config)."
  value       = hcloud_network.cluster.id
}

output "kubeconfig_hint" {
  value = "scp root@${hcloud_server.master.ipv4_address}:/etc/rancher/k3s/k3s.yaml ./kubeconfig && sed -i '' 's/127.0.0.1/${hcloud_server.master.ipv4_address}/' ./kubeconfig"
}
