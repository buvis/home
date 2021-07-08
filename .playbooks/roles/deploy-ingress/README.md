Deploy ingress
==============

Installs nginx-ingress as it is more flexible than k3s default.

Requirements
------------

Make sure that host has pip and PyYAML installed.

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
    - role: deploy-ingress
```

License
-------

BSD

Author Information
------------------

Authored by Tomáš Bouška (https://buvis.net)
