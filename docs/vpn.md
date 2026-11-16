# VPN deployment guide

**A VPN connection with a working kill switch is highly recommended for BOTH Jackett's indexer
traffic and qBittorrent's torrent traffic.** It is optional and provider independent.

## What Torrent Tools does and does not do

* It calls the local APIs of your Jackett and qBittorrent. Those services and your network
  deployment decide where traffic goes.
* Home Assistant never contacts indexers, trackers or arbitrary download links itself.
  Jackett resolves its own download references; the integration only reads the redirect.
* It does **not** create a VPN, verify leak protection, or provide a kill switch. Optional VPN
  monitoring may come later; it is not part of v1.
* No provider, VPN credential, sensor or container name is required.

## Example: Gluetun

[`examples/docker-compose.gluetun.yml`](../examples/docker-compose.gluetun.yml) runs Gluetun and puts
**both** qBittorrent and Jackett in its network namespace (`network_mode: "service:gluetun"`).

Adapt:

1. `VPN_SERVICE_PROVIDER`, `VPN_TYPE`, credentials and server selection: see the
   [Gluetun wiki](https://github.com/qdm12/gluetun-wiki) for your provider. Put secrets in a
   `.env` file that is not committed.
2. `FIREWALL_OUTBOUND_SUBNETS`: your LAN subnet (the example uses the documentation range
   `192.0.2.0/24`), so Home Assistant can reach the published ports. Never `0.0.0.0/0`.
3. `ports`: published on **one LAN address** only. Do not forward these ports on your router and do
   not expose Jackett or qBittorrent to the internet. Both APIs are only for the local network.
4. DNS: the example enables Gluetun's DNS-over-TLS so lookups use the tunnel. Check your
   provider's recommendation.
5. Pin tested image versions.
6. In Torrent Tools use `http://<lan address>:8080` and `http://<lan address>:9117`.

Gluetun's built-in firewall blocks traffic that does not use the tunnel, and containers that
share its namespace have no other route. That is the design intent, but **sharing a network
stack is not proof**. Test it.

## Manual leak test (do this before trusting it)

Do it on the host that runs the stack, with no downloads you care about running.

1. **Tunnel up.** From inside each service's namespace, confirm the public IP is the VPN's, not
   your home IP:
   `docker exec gluetun wget -qO- https://ifconfig.me` and compare with your real IP from another device.
   Repeat for the services through a container that has `wget`/`curl`, or use
   `docker run --rm --network container:qbittorrent <image-with-curl> curl -s https://ifconfig.me`
   (and `container:jackett`).
2. **Tunnel down.** Break the tunnel without stopping the firewall: for example block the VPN
   endpoint on the host firewall, or `docker exec gluetun sh -c 'ip link set tun0 down'`
   (interface name varies: WireGuard is often `wg0`). Do not just stop the Gluetun container; that
   also removes the network, which proves less.
3. **While down**, repeat the public-IP request from inside both service namespaces and a DNS
   lookup (`nslookup example.com`). Expected: **timeouts or failures, never your home IP**.
   Also confirm qBittorrent shows no peers and a Jackett search fails.
4. **Restore** the tunnel; check traffic resumes and the IP is the VPN's again.
5. Repeat after a Gluetun/Docker/host restart, and when Gluetun restarts while the services run.

If any step shows your real IP, stop and fix before using the stack. This guide cannot verify
your deployment for you.

## Existing topologies

If Jackett already goes through a separate VPN container, keep it. The integration only needs
reachable URLs and your API credentials. Make sure qBittorrent is protected as well; the
integration cannot tell. Do not rely on this document as evidence that an existing qBittorrent
setup has a verified kill switch.

## Behaviour when the VPN is down

Searches fail with "Jackett could not be reached / did not answer"; qBittorrent calls report
unavailable or uncertain outcomes. Setup retries automatically once services return.
