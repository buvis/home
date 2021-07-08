Deploy PiHole
==============

Installs PiHole adblocker as primary and secondary DNS servers. See: https://github.com/MoJo2600/pihole-kubernetes

Requirements
------------

Make sure that host has pip and PyYAML installed. Persistence must be available at NAS over NFS.

Role Variables
--------------

The file `vars/main.yaml` contains variables with descriptive names, so there is no need to document them here.

Dependencies
------------

This requires kubernetes.core collection. To install it use: `ansible-galaxy collection install kubernetes.core`

Example Playbook
----------------

```
- hosts: chief
  remote_user: "{{ default_user }}"
  become: false
  gather_facts: true

  pre_tasks:
    - name: prepare for deployment by helm
      import_tasks: tasks/prepare-for-deploy-by-helm.yaml

  roles:
    - role: deploy-pihole
```

License
-------

BSD

Author Information
------------------

Authored by Tomáš Bouška (https://buvis.net)
