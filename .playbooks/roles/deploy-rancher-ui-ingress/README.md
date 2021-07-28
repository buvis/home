Deploy Rancher UI ingress
=========================

Deploys ingress to Rancher UI which is running externally, not in cluster.

Requirements
------------

Make sure that host has pip and PyYAML installed.

Role Variables
--------------

None.

Dependencies
------------

None.

Example Playbook
----------------

```
- hosts: chief
  remote_user: "{{ default_user }}"
  become: false
  gather_facts: true

  roles:
    - role: deploy-rancher-ui-ingress
```

License
-------

BSD

Author Information
------------------

Authored by Tomáš Bouška (https://buvis.net)
