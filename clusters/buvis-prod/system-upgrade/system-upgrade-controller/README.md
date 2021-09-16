## Prepare the nodes
1. Label masters for k3s server upgrades: `kubectl label nodes <MASTER_NODE> plan.upgrade.cattle.io/k3s-server=enabled`
2. Label workers for k3s agent upgrades: `kubectl label nodes <WORKER_NODE> plan.upgrade.cattle.io/k3s-agent=enabled`
3. Label archlinux nodes (currently all of them): `kubectl label nodes <NODE> plan.upgrade.cattle.io/archlinux=enabled`
4. You need to do that only once in node's lifetime

## Upgrade k3s
1. Email is sent for releases watch on https://github.com/k3s-io/k3s
2. Update version in `~/clusters/buvis-prod/system-upgrade/system-upgrade-controller/plans/k3s.yaml`
3. Apply the plan: `kubectl apply -f clusters/buvis-prod/system-upgrade/system-upgrade-controller/plans/k3s.yaml`

## Upgrade system
1. Update version in `~/clusters/buvis-prod/system-upgrade/system-upgrade-controller/plans/archlinux.yaml` to today's date in yyyymmdd format
2. Apply the plan: `kubectl apply -f clusters/buvis-prod/system-upgrade/system-upgrade-controller/plans/archlinux.yaml`

## Troubleshooting
- observe the upgrade: `kubectl get all -n system-upgrade`
- it seems deleting the jobs that are stuck is tolerated by the controller, but being patient (default poll interval is 15 minutes) is preferred
