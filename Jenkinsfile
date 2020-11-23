// boulder module names that require building go binary from source
moduleNamesWithBinary = ['akamai-purger', 'boulder-ca', 'boulder-publisher', 'boulder-ra', 'boulder-sa', 'boulder-va', 'boulder-wfe2', 'ct-test-srv', 'nonce-service', 'ocsp-responder']
// boulder module names that do not require building go binary from source
moduleNamesWithoutBinary = ['boulder-logger', 'boulder-hsm']

// generates docker image build stages for parallel execution
def generateImageBuildStages(moduleNames) {
  // assemble build stages in a map
  moduleStages = [:]
  // module build stages with boulder binaries
  for (moduleName in moduleNames) {
    // stage name is the module's name
    moduleStages["${moduleName}"] = {
      stage("Building ${moduleName} image") {
        // only unstash if module had its binary compiled just now
         if(moduleNamesWithBinary.contains("${moduleName}")) {
            unstash name: "${moduleName}"
         }
        // use the builder pod's kaniko container
         container('kaniko') {
           checkout scm
           def dockerFilePath = "build/Dockerfile.${moduleName}"
           sh """#!/busybox/sh
           /kaniko/executor --context `pwd` --dockerfile=`pwd`/${dockerFilePath} --cleanup --registry-certificate=harbor.prod.internal.great-it.com=/etc/tls-trust.pem --destination=${env.REGISTRY}/certology/${moduleName}:${env.VERSION} --cache --registry-mirror ${env.REGISTRY_MIRROR}
           """
         }
      }
    }
  }
  return moduleStages
}

pipeline {
  agent any
  triggers {
    githubPush()
  }
  parameters {
    string(name: 'GO_VERSION', defaultValue: '1.15.4', description: 'Golang compiler version')
    string(name: 'KANIKO_VERSION', defaultValue: 'debug-v1.3.0', description: 'Kaniko image version')
  }
  environment {
    // build variables
    RELEASE_NAME = "certology-${env.BUILD_NUMBER}"
    VERSION = "${TAG_NAME ?: 'latest'}"
    // infrastructure services
    GITHUB_USERNAME = 'great-bot'
    GITHUB_TOKEN = credentials('great-bot-github-token')
    GOPROXY = 'http://goproxy.prod.internal.great-it.com'
    REGISTRY = 'harbor.prod.internal.great-it.com'
    REGISTRY_MIRROR = 'registry.prod.internal.great-it.com'
  }
  options {
    ansiColor('xterm')
  }
  stages {
    stage('Compile code') {
      agent {
        kubernetes {
          yaml """
apiVersion: v1
kind: Pod
spec:
  containers:
    - name: go-compiler
      image: golang:${params.GO_VERSION}
      command:
        - cat
      tty: true
"""
        }
      }
      steps {
        container("go-compiler") {
          sh "git config --global url.'https://${GITHUB_USERNAME}:${GITHUB_TOKEN}@github.com/'.insteadOf 'https://github.com/'"
          sh "make"
          script {
            for (moduleName in moduleNamesWithBinary) {
              stash name: "${moduleName}", includes: "bin/${moduleName}"
            }
          }
        }
      }
    }
    stage('Build images') {
      agent none
      stages {
        stage('Parallel image building') {
          steps {
            script {
              // assemble all module names
              def moduleNames = []
              moduleNames += moduleNamesWithBinary
              moduleNames += moduleNamesWithoutBinary
              podTemplate(yaml: """
apiVersion: v1
kind: Pod
spec:
  containers:
    - name: kaniko
      image: harbor.prod.internal.great-it.com/library/kaniko-project/executor:${params.KANIKO_VERSION}
      command:
        - /busybox/cat
      tty: true
      env:
        - name: DOCKER_CONFIG
      value: /kaniko/.docker
      volumeMounts:
        - name: jenkins-docker-cfg
          mountPath: /kaniko/.docker
  volumes:
    - name: jenkins-docker-cfg
      projected:
        sources:
          - secret:
              name: harbor-certology-robot-docker-credentials
              items:
                - key: .dockerconfigjson
                  path: config.json
"""
              ) 
              {
                node(POD_LABEL) {
                  parallel generateImageBuildStages(moduleNames)
                }
              }
            }
          }
        }
      }
    }
  }
  post {
    regression {
      slackSend(channel: '#certology', notifyCommitters: true, color: '#FF0000', message: "Build Regression - ${env.JOB_NAME} ${env.BUILD_NUMBER} (<${env.BUILD_URL}|Open>)")
    }
    fixed {
      slackSend(channel: '#certology', notifyCommitters: true, color: '#00FF00', message: "Build Fixed - ${env.JOB_NAME} ${env.BUILD_NUMBER} (<${env.BUILD_URL}|Open>)")
    }
  }
}
