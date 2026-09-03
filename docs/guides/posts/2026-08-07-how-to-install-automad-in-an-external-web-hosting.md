---
title: "How to install Automad in an external web hosting"
date: 2026-08-07
description: "Step-by-step guide to installing Automad CMS on external web hosting."
tags:
  - Automad CMS
  - Server
  - Tech
  - Web
---



# {{ $frontmatter.title }}

### {{ new Date($frontmatter.date).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }) }}



## For this tutorial, I'm going to use InfinityFree as an example, please note that some hosting providers have different features too!

## 1. Prepare your hosting and files

Download Automad's zip, set up your hosting, popular hosting options include: GoDaddy, Cloudzy, Hostinger, iFastNet (InfinityFree), ...etc

## 2. Install Automad

<img src="/assets/images/guides/how-to-install-automad/image-1786032333725.webp" alt="InfinityFree's default file manager UI" width="1844" height="989" loading="lazy">

To install Automad on your hosting, go to the file manager, put the Automad zip on the public root directory (usually `.htdocs`). Depending on your file manager, there will be an extract option or upload zip, then extract, like this:

<img src="/assets/images/guides/how-to-install-automad/image-1786032457878.webp" alt="Extracting Automad zip" width="1290" height="925" loading="lazy">

Now, go to `your-domain.tld/dashboard` (or `your.sub.domain/dashboard`) to access the Automad dashboard, then create your new user and download the accounts file.

<img src="/assets/images/guides/how-to-install-automad/image-1786032783006.webp" alt="Automad dashboard" width="846" height="785" loading="lazy">

Now, back to the file manager

<img src="/assets/images/guides/how-to-install-automad/image-1786032897173.webp" alt="File manager" width="1521" height="862" loading="lazy">

Upload your `accounts.php` to exactly the `config` folder

<img src="/assets/images/guides/how-to-install-automad/image-1786032958457.webp" alt="Uploading accounts.php" width="1513" height="361" loading="lazy">

## 3. Finish setup, sign in and have fun creating your Automad website!

<img src="/assets/images/guides/how-to-install-automad/image-1786033042153.webp" alt="Automad setup complete" width="719" height="363" loading="lazy">