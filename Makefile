DOCKER_USERNAME ?= abyrne_openshift
APPLICATION_NAME ?= verifier-log-analysis
GIT_HASH ?= $(shell git log --format="%h" -n 1)

build:
	podman build --tag ${DOCKER_USERNAME}/${APPLICATION_NAME}:${GIT_HASH} .

run:
	podman run -it --rm ${DOCKER_USERNAME}/${APPLICATION_NAME}:${GIT_HASH}

