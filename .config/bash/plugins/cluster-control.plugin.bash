cite about-plugin
about-plugin 'buvis cluster management'

# get cpu temperature of all nodes in the cluster
function buvis-get-temp () {
    cd $DOTFILES_ROOT/.playbooks
    ansible-playbook get-cluster-temperature.yaml
    cd -
}

# get reboot plan
function buvis-get-reboot-plan () {
    RED='\033[1;31m'
    GREEN='\033[1;32m'
    NC='\033[0m'
    hosts=( columbus nimitz feynman hawking planck braun )

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
    cd $DOTFILES_ROOT/git/src/gitlab.com/buvis/playbooks
    ansible -b -m reboot $1
    cd -
}

# shutdown a node
function buvis-shutdown () {
    cd $DOTFILES_ROOT/.playbooks
    ansible -b -m shell -a "shutdown now" $1
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

function buvis-get-rbd-image-for-pvc () {
    PVC=$1
    kubectl get pv/$(kubectl get pv | grep ${PVC} | awk -F' ' '{print $1}') -n home -o json | jq -r '.spec.csi.volumeAttributes.imageName'
}
