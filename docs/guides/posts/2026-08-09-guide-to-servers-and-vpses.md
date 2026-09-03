---
title: "Guide to servers and VPSes"
date: 2026-08-09
description: "Everything you need to know about servers and VPSes for hosting your projects."
tags:
  - Linux
  - Server
  - Tech
  - Windows
---



# {{ $frontmatter.title }}

### {{ new Date($frontmatter.date).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }) }}

<div v-if="$frontmatter.tags" class="blog-post-tags">
  <a v-for="tag in $frontmatter.tags" :key="tag" :href="`/tags/${encodeURIComponent(tag)}/`" class="blog-post-tag">#{{ tag }}</a>
</div>



## This will be the last guide you will read on servers and VPSes, I guess...?

### What are servers?

Servers are another type of computers, they can come with multiple forms: racks, towers, small, or even clusters.

Unlike traditional desktops and laptops, servers are overkill for basic work. Which is why servers often come with no display by default, which means it's more focused on remote management.

Some server setups also have a monitor, which is very useful for debugging issues with network, BIOS, and other things that you can't fix remotely.

KVMs also exist, so it is the closest to fixing these kinds of issues remotely.

### But wait, there's more!

These forms of servers are the most common on server rooms. But that doesn't stop you from turning an old laptop or desktop to a server.

### How can I start getting a server?

You can buy  dedicated server hardware with Intel Xeon or AMD EPYC, but they're usually very expensive to buy and maintain.

Another way is to turn your old but capable hardware to a server, it's way cheaper, but power consumption can depend on the machine and the specs.

VPSes also exist, you sign up on the provider, and get a plan, but it will bill you by month so be careful on your bank account!

### I'm getting a dedicated server, what should I aim for?

For dedicated server racks, towers or small efficient servers, aim for:

- Reliability
- Performance
- Power consumption and efficiency
- Storage
- Futureproofability
- Budget fit

The same goes with using your old computer as a server too!

**WARNING!**

If your desktop/server's PSU is very old, please buy a new one! Desktop PSUs often last from 5 to 15 years.

A new PSU always beat an used one because new ones often age better than buying used.

### I'm getting a VPS, what should I aim for?

If you are getting a VPS, you should primarily aim for:

- Reliability
- Performance
- Price per month
- Plans
- Specs
- Perks
- Customer support

If you don't know what provider to use, I suggest you to use:

- Linode (Now Akamai Cloud) - Linux-based VPSes with good software selection and user-friendly UI, free with 100$ credit, rest pay-as-you-go
- GCP - Is both free and pay-as-you-go
- Azure - Same with GCP
- Oracle Cloud - Free forever and pay-as-you-go, but can be unreliable
- Vultr - Free 300$ credits, rest pay-as-you-go

### Hey, I'm a noob at servers, how can I start hosting services easily?

If you want to start hosting services, you should check out the [awesome-selfhosted repository on GitHub](https://github.com/awesome-selfhosted/awesome-selfhosted).

If you're still unsure, here's what you should host:

### 1. Management choices

- Debian + CasaOS (If you're familiar with Docker and Debian) - most common
- Any Linux distribution + Portainer (More common on Docker setups) - also very common
- Any Linux distribution + Cockpit (RHEL's Cockpit specifically, you may get confused by the CMS also named that) - less common, but it's more extendable
- Any Linux distribution + YunoHost - less common

### 2. Networking software

- Tailscale (WireGuard-based mesh VPN)
- NetBird (also a mesh VPN)
- Cloudflare tunnels (more common on HTTP/HTTPS stuffs)

### 3. Maintenance software

- smartctl (Storage device SMART status)
- cURL (fetch URLs)
- firewalld/ufw (Firewall utility)