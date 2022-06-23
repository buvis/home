cite about-plugin
about-plugin 'mopidy players management'

# print container log from remote machine
function print-mopidy-log () {
    ssh $1 'docker logs $(docker ps -f name=mopidy | cut -d " " -f1 | tail -n 1)'
}

# run/update Mopidy with Snapserver at remote machine
function make-mopidy () {
    cd $DOTFILES_ROOT/.playbooks
    ansible-playbook -i $1, make-music-server.yaml
    cd -
    echo "Don't forget to authenticate to Tidal in the next 5 minutes.\n"
    echo "Get the OAuth link from the logs: ssh $1 docker logs mopidy"
}

# scan local library
function scan-mopidy () {
    ssh $1 "docker exec mopidy /shim/scan-local.sh"
}
