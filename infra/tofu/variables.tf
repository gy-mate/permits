variable "hcloud_token" {
  description = "Hetzner Cloud API token (read/write)."
  type        = string
  sensitive   = true
}

variable "cloudflare_api_token" {
  description = "Cloudflare API token scoped to Zone:DNS:Edit for your domain."
  type        = string
  sensitive   = true
}

variable "cloudflare_zone_id" {
  description = "Cloudflare zone id for your domain."
  type        = string
}

variable "hostname" {
  description = "Public hostname for the API (a subdomain like permits.example.com or a root domain like permits.com)."
  type        = string
}

variable "ssh_public_key" {
  description = "SSH public key used to access the nodes."
  type        = string
}

variable "location" {
  description = "Hetzner location (must offer CX23 / x86)."
  type        = string
  default     = "fsn1"
}

variable "server_type" {
  description = "Server type for both master and workers."
  type        = string
  default     = "cx23"
}

variable "k3s_token" {
  description = "Shared secret joining k3s agents to the server."
  type        = string
  sensitive   = true
}
