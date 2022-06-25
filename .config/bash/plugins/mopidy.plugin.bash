cite about-plugin
about-plugin 'mopidy players management'

# print container log from remote machine
function mopidy-print-log () {
    ssh $1 'docker logs $(docker ps -f name=mopidy | cut -d " " -f1 | tail -n 1)'
}

# run/update Mopidy with Snapserver at remote machine
function mopidy-make () {
    cd $DOTFILES_ROOT/.playbooks
    ansible-playbook -i $1, make-music-server.yaml
    cd -
    echo "Don't forget to authenticate to Tidal in the next 5 minutes.\n"
    echo "Get the OAuth link from the logs: ssh $1 docker logs mopidy"
}

# scan local library
function mopidy-rescan () {
    case $1 in
        buvis)
            cd $DOTFILES_ROOT/git/src/github.com/buvis/clusters/production
            direnv allow . && eval "$(direnv export bash)"
            kubectl exec -n media deploy/mopidy -- /shim/scan-local.sh
            cd -
            ;;
        *)
            ssh $1 "docker exec mopidy /shim/scan-local.sh"
            ;;
    esac
}
