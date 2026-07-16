resource "hcloud_ssh_key" "default" {
  name       = "permits"
  public_key = var.ssh_public_key
}

resource "hcloud_network" "cluster" {
  name     = "permits"
  ip_range = "10.0.0.0/16"
}

resource "hcloud_network_subnet" "cluster" {
  network_id   = hcloud_network.cluster.id
  type         = "cloud"
  network_zone = "eu-central"
  ip_range     = "10.0.0.0/24"
}

resource "hcloud_placement_group" "cluster" {
  name = "permits"
  type = "spread"
}

# Allow SSH, the k3s API, and HTTP/HTTPS to the cluster. Postgres (5432) is exposed
# publicly via the Hetzner LB the CCM provisions; it is intentionally reachable

resource "hcloud_firewall" "cluster" {
  name = "permits"

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "22"
    source_ips = ["0.0.0.0/0", "::/0"]
  }
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "6443"
    source_ips = ["0.0.0.0/0", "::/0"]
  }
}

resource "hcloud_server" "master" {
  name               = "permits-master"
  server_type        = var.server_type
  image              = "debian-13"
  location           = var.location
  ssh_keys           = [hcloud_ssh_key.default.id]
  placement_group_id = hcloud_placement_group.cluster.id
  firewall_ids       = [hcloud_firewall.cluster.id]

  user_data = templatefile("${path.module}/cloud-init/master.yaml.tftpl", {
    k3s_token = var.k3s_token
  })

  labels = {
    cluster = "permits"
    role    = "master"
  }

  network {
    network_id = hcloud_network.cluster.id
    ip         = "10.0.0.2"
  }

  depends_on = [hcloud_network_subnet.cluster]
}
