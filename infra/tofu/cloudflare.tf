# The Hetzner Cloud LB IP only exists after the Cloud Controller Manager provisions
# it for the ingress-nginx Service. After deploying ingress (see README), read its IP
# and set `lb_ipv4` / `lb_ipv6`, then re-apply to publish the DNS records

variable "lb_ipv4" {
  description = "Public IPv4 of the ingress LoadBalancer (set after ingress is up)."
  type        = string
  default     = ""
}

variable "lb_ipv6" {
  description = "Public IPv6 of the ingress LoadBalancer (set after ingress is up)."
  type        = string
  default     = ""
}

resource "cloudflare_dns_record" "permits_a" {
  count   = var.lb_ipv4 == "" ? 0 : 1
  zone_id = var.cloudflare_zone_id
  name    = var.hostname
  type    = "A"
  content = var.lb_ipv4
  ttl     = 1
  # DNS-only (grey cloud) so the Let's Encrypt DNS-01 challenge and the LB work cleanly.
  proxied = false
}

resource "cloudflare_dns_record" "permits_aaaa" {
  count   = var.lb_ipv6 == "" ? 0 : 1
  zone_id = var.cloudflare_zone_id
  name    = var.hostname
  type    = "AAAA"
  content = var.lb_ipv6
  ttl     = 1
  proxied = false
}
