cite about-plugin
about-plugin 'buvis cluster management'

# get cpu temperature of all nodes in the cluster
function buvis-get-temp () {
    cd $DOTFILES_ROOT/git/src/github.com/buvis-net/clusters/production/infrastructure/ansible
    ansible-playbook get-cluster-temperature.yaml
    cd -
}

# get reboot plan
function buvis-get-reboot-plan () {
    RED='\033[1;31m'
    GREEN='\033[1;32m'
    NC='\033[0m'
    hosts=( hawking columbus feynman planck buvis-master-1 buvis-worker-1 buvis-worker-2 buvis-worker-3 )

    for host in "${hosts[@]}"
    do
        if (ssh $host cat /var/run/reboot-required 2>/dev/null); then
            echo -e "${RED}$host plans to restart${NC}"
        else
            echo -e "${GREEN}$host doesn't plan to restart${NC}"
        fi
    done
}

# reboot a node
function buvis-reboot () {
    cd $DOTFILES_ROOT/git/src/github.com/buvis-net/clusters/production/infrastructure/ansible
    ansible -b -m reboot $1
    cd -
}

# reconcile flux
function buvis-reconcile () {
    cd $DOTFILES_ROOT/git/src/github.com/buvis-net/clusters/production
    flux reconcile ks flux-system --with-source
    cd -
}

# shutdown a node
function buvis-shutdown () {
    cd $DOTFILES_ROOT/git/src/github.com/buvis-net/clusters/production/infrastructure/ansible
    ansible -b -m shell -a "shutdown now" $1
    cd -
}

# upgrade cluster nodes
function buvis-upgrade () {
    cd $DOTFILES_ROOT/git/src/github.com/buvis-net/clusters/production/infrastructure/ansible
    ansible-playbook upgrade-cluster-nodes.yaml
    cd -
}

# force deletion of namespace without resources
function buvis-delete-namespace () {
    NAMESPACE=$1
    kubectl get namespace $NAMESPACE 2>&1 1>/dev/null
    if [ $? -eq 0 ]; then
        resources=`kubectl get all -n $NAMESPACE 2>&1 | head -n 1`
        if [[ $resources = "No resources found in $NAMESPACE namespace." ]]; then
            kubectl get namespace $NAMESPACE -o json > $NAMESPACE.json
            sed -i -e 's/"kubernetes"//' $NAMESPACE.json
            kubectl replace --raw "/api/v1/namespaces/$NAMESPACE/finalize" -f ./$NAMESPACE.json
            rm $NAMESPACE.json
        else
            echo "There are still resources in $NAMESPACE namespace. Remove them first."
        fi
    fi
}
