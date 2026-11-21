pipeline {
    agent { label 'docker' }
    options {
        timestamps()
        timeout(time: 30, unit: 'MINUTES')
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '10'))
        skipStagesAfterUnstable()
    }
    parameters {
        choice(name: 'SUITE', choices: ['local', 'smoke', 'regression'], description: 'local — без публичных сайтов; smoke/regression — живые стенды')
        choice(name: 'TARGET', choices: ['external', 'demoqa', 'reqres', 'fakestore'], description: 'Все сайты или один')
        choice(name: 'WORKERS', choices: ['0', '2'], description: '0 — последовательно, 2 — два worker; учитывать квоты API')
        booleanParam(name: 'RUN_SELENOID', defaultValue: true, description: 'Remote Chrome: local fixture; для DemoQA также внешний smoke')
        booleanParam(name: 'TEST_EVENTS', defaultValue: false, description: 'Сохранить события в outbox для Kafka')
    }
    environment {
        ARTIFACTS = "artifacts/${BUILD_NUMBER}"
        PYTHON = "python"
    }
    stages {
        stage('Playwright and API') {
            agent {
                dockerfile {
                    filename 'Dockerfile'
                    args '--ipc=host'
                    reuseNode true
                }
            }
            stages {
                stage('Project checks') {
                    steps {
                        sh 'make check'
                    }
                }
                stage('Local HTTP and Chromium') {
                    steps {
                        sh 'make integration-tests'
                    }
                }
                stage('Smoke') {
                    when { expression { params.SUITE != 'local' } }
                    steps {
                        sh 'make smoke'
                    }
                }
                stage('Regression') {
                    when { expression { params.SUITE == 'regression' } }
                    steps {
                        // Smoke уже прошёл: запускаем остальные проверки без повторения.
                        sh 'make regression-rest'
                    }
                }
            }
        }
        stage('Selenoid') {
            when { expression { params.RUN_SELENOID } }
            steps {
                script {
                    def external = params.SUITE != 'local' && (params.TARGET in ['external', 'demoqa'])
                    def markers = external ? 'selenoid' : 'selenoid and not external'
                    def project = ('selenoid-' + env.BUILD_TAG).toLowerCase().replaceAll('[^a-z0-9-]', '-')
                    withEnv(["SELENOID_PROJECT=${project}", 'SELENOID_PORT=0', "SELENOID_MARKERS=${markers}"]) {
                        sh 'sh infra/selenoid/run.sh'
                    }
                }
            }
        }
    }
    post {
        always {
            archiveArtifacts artifacts: "${env.ARTIFACTS}/**", allowEmptyArchive: true
            junit testResults: "${env.ARTIFACTS}/*.xml", allowEmptyResults: true
            script {
                if (fileExists("${env.ARTIFACTS}/allure-results")) {
                    def paths = ['integration', 'smoke', 'regression-rest', 'selenoid'].collect {
                        "${env.ARTIFACTS}/allure-results/${it}"
                    }.findAll { fileExists(it) }
                    if (paths) {
                        allure commandline: 'allure2', results: paths.collect { [path: it] }
                    }
                }
            }
        }
    }
}
