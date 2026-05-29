# Пререквизиты для разворачивания стенда на DKP/DVP

Этот документ описывает требования к новому стенду DKP/DVP, на который переносится демо Argo CD + AWX + GitOps + DVP + self-service portal.

## Целевая модель

На новом стенде должны быть доступны:

- Kubernetes API, управляемый через `kubectl`;
- DKP с включенными базовыми модулями для Ingress, Dex/OIDC и сертификатов;
- DVP с CRD `virtualization.deckhouse.io`;
- StorageClass для Gitea, AWX PostgreSQL, AWX projects PVC и DVP `VirtualDisk`;
- DNS или `/etc/hosts` записи для Gitea, Argo CD, AWX и self-service portal;
- egress до внешних registry и URL образов, если образы не зеркалируются во внутренний контур;
- права администратора кластера на время установки стенда.

## Рабочая станция оператора

На машине, с которой выполняется перенос, должны быть установлены:

| Инструмент | Для чего нужен | Проверка |
| --- | --- | --- |
| `kubectl` | Управление кластером и проверка ресурсов | `kubectl version --client` |
| `git` | Работа с GitHub/Gitea и перенос репозитория | `git --version` |
| `curl` | Вызовы API Gitea/AWX | `curl --version` |
| `jq` | Разбор JSON в bootstrap-скриптах | `jq --version` |
| `base64` | Декодирование Kubernetes Secret | `base64 --help` |
| `sed`, `rg` или `grep` | Массовая проверка hardcoded значений | `rg --version` или `grep --version` |

Доступ к кластеру:

```bash
kubectl config get-contexts
kubectl config current-context
kubectl get nodes -o wide
```

## Kubernetes и DKP

Минимальные требования:

| Требование | Зачем нужно | Проверка |
| --- | --- | --- |
| Рабочий kube-context | Все скрипты используют Kubernetes API | `kubectl get nodes` |
| Права cluster-admin на установку | Создаются CRD, ClusterRole, ClusterRoleBinding, namespaces | `kubectl auth can-i '*' '*' --all-namespaces` |
| Ingress controller с class `nginx` или адаптированный class | Публикация Gitea, Argo CD, AWX, portal, demo-app | `kubectl get ingressclass` |
| DKP Dex/OIDC | Авторизация self-service portal через `DexAuthenticator` | `kubectl api-resources | grep -i dexauthenticator` |
| DKP User/Group CRD, если используются demo-пользователи | Создание `alice-koroleva`, `boris-smirnov`, `marina-volkova` | `kubectl api-resources | grep -E 'users|groups'` |
| cert-manager или DKP certificate support | TLS для `selfservice-*` и корректный Dex callback | `kubectl api-resources | grep certificates` |
| Рабочий DNS или возможность обновить `/etc/hosts` | Доступ к UI и Ingress hostnames | `kubectl get ingress -A` |

Если на целевом стенде IngressClass называется не `nginx`, нужно заменить его в:

```text
manifests/dkp/ingresses.yaml
gitops/environments/prod/demo-app.yaml
gitops/environments/prod/tenants/customer-a/app.yaml
gitops/self-service/portal/ingress.yaml
gitops/self-service/portal/dex-authenticator.yaml
gitops/self-service/portal/app/server.py
gitops/self-service/generated/*/app.yaml
```

## DVP

На стенде должен быть включен DVP и доступны CRD:

```bash
kubectl api-resources | grep -E 'virtualmachines|virtualdisks|virtualimages|clustervirtualimages'
```

Ожидаемые API-объекты:

- `VirtualImage`;
- `ClusterVirtualImage`;
- `VirtualDisk`;
- `VirtualMachine`;
- `VirtualMachineClass`.

Проверка класса VM:

```bash
kubectl get virtualmachineclass
```

В текущих манифестах используется:

```yaml
virtualMachineClassName: generic
```

Если на целевом стенде нет класса `generic`, заменить его в:

```text
gitops/environments/prod/dvp-postgres-vm.yaml
gitops/environments/prod/golden-images/builder-vm.yaml
gitops/self-service/portal/app/server.py
gitops/self-service/generated/*/vm.yaml
```

## Storage

В текущем стенде используется StorageClass:

```text
k8nfs
```

Он указан явно в:

```text
manifests/awx/awx.yaml
manifests/awx/projects-pvc.yaml
gitops/environments/prod/dvp-postgres-vm.yaml
gitops/environments/prod/golden-images/builder-vm.yaml
gitops/self-service/portal/deployment.yaml
gitops/self-service/portal/app/server.py
gitops/self-service/generated/*/vm.yaml
```

На новом стенде нужно либо создать StorageClass `k8nfs`, либо заменить значение на фактический StorageClass.

Проверка:

```bash
kubectl get storageclass
kubectl get storageclass k8nfs
```

Рекомендации по объему:

| Потребитель | Запрос в манифестах | Комментарий |
| --- | ---: | --- |
| Gitea PVC | `2Gi` | Репозиторий и sqlite data |
| AWX PostgreSQL | `4Gi` | В `manifests/awx/awx.yaml` |
| AWX projects PVC | `2Gi` | Сейчас отдельный пример PVC |
| `postgres-vm-root` | `256Mi` | Минимальный DVP disk |
| `golden-builder-root` | `256Mi` | Builder disk, VM остановлена вручную |
| Self-service VM disk | `256Mi` на VM | По одной VM на профиль `app-with-vm` |

Практический минимум для чистого демо: 20Gi свободного persistent storage. Комфортный запас: 50Gi и больше, особенно если планируются дополнительные DVP images и несколько self-service VM.

## Сетевой доступ и registry

Кластеру нужен egress до:

| Назначение | Для чего |
| --- | --- |
| `github.com` | AWX operator kustomize install и внешний GitHub remote |
| `quay.io` | AWX EE и auxiliary images |
| `gitea/gitea` registry | Gitea image |
| `dl-cdn.alpinelinux.org` | Импорт Alpine cloud image для DVP |
| GitHub `kirka1206/ArgoAWXk8sDVPdemo` | Клонирование исходного проекта, если используется GitHub |

Если стенд закрытый, заранее зеркалировать images и cloud image во внутренние registry/HTTP storage, затем заменить URL в:

```text
gitops/environments/prod/dvp-postgres-vm.yaml
gitops/environments/prod/golden-images/source-image.yaml
gitops/environments/prod/golden-images/cluster-source-image.yaml
scripts/bootstrap.sh
manifests/gitea/gitea.yaml
manifests/awx/awx.yaml
```

## DNS и имена

Текущий стенд использует домен:

```text
d8.kir.lab
```

Текущие hostnames:

| Host | Назначение |
| --- | --- |
| `gitea-awx.d8.kir.lab` | Gitea UI/API |
| `argocd-awx.d8.kir.lab` | Argo CD UI |
| `awx-demo.d8.kir.lab` | AWX UI/API |
| `selfservice-awx.d8.kir.lab` | Self-service portal |
| `*.d8.kir.lab` | Self-service app ingress hosts |

На новом стенде выбрать новый домен, например:

```text
demo.example.lab
```

И подготовить записи:

```text
<INGRESS_IP> gitea-awx.demo.example.lab
<INGRESS_IP> argocd-awx.demo.example.lab
<INGRESS_IP> awx-demo.demo.example.lab
<INGRESS_IP> selfservice-awx.demo.example.lab
<INGRESS_IP> dev-alice-koroleva-feature-demo.demo.example.lab
```

Если wildcard DNS недоступен, для каждого self-service стенда нужно добавлять отдельную запись.

## Git и репозитории

В текущем демо есть два remote:

| Remote | Назначение |
| --- | --- |
| `origin` | GitHub `kirka1206/ArgoAWXk8sDVPdemo` |
| `dkp-gitea` | Внутренний Gitea стенда |

Argo CD читает именно внутренний Gitea:

```text
http://gitea-http.gitea.svc.cluster.local:3000/codex/demo.git
```

Для нового стенда нужно сохранить owner/repo `codex/demo` или поменять `repoURL` в:

```text
manifests/argocd/application-demo.yaml
manifests/argocd/application-demo-platform.yaml
scripts/bootstrap.sh
gitops/self-service/portal/deployment.yaml
```

## Секреты и пользователи

В Git не должны попадать реальные пароли и токены.

Перед запуском self-service portal нужно создать Secret для доступа backend к Gitea:

```bash
kubectl create namespace self-service-portal --dry-run=client -o yaml | kubectl apply -f -
kubectl -n self-service-portal create secret generic self-service-portal-gitea \
  --from-literal=username=codex \
  --from-literal=password='<gitea-password>' \
  --dry-run=client -o yaml | kubectl apply -f -
```

Demo users для Dex задаются через CRD `User` и `Group`. В Git есть только пример:

```text
gitops/self-service/portal/dex-demo-users.example.yaml
```

Перед применением заменить `replace-with-bcrypt-hash` на реальные bcrypt-хэши или создать пользователей штатным способом целевого DKP.

## AWX

Bootstrap создаёт pod-only AWX объекты:

- Project `Gitea demo repo`;
- Inventory `Demo OS pods`;
- Credential `demo-pod-ssh`;
- Job Template `Configure OS pods`.

Для DVP VM и golden image сценариев после разворачивания нужно вручную или отдельным скриптом создать:

- Inventory `DVP VMs`;
- Host `postgres-vm` с актуальным `ansible_host`;
- Credential `dvp-vm-ssh`;
- Job Template `Bootstrap DVP VM`;
- Inventory `Golden Image Builders`;
- Host `golden-builder`;
- Job Template `Prepare Golden Image`;
- Job Template `Validate Golden Image`.

AWX подключается к Git как Project и берет playbooks из:

```text
gitops/awx/playbooks/
```

## Проверка готовности стенда

Перед переносом выполнить:

```bash
kubectl get nodes -o wide
kubectl get storageclass
kubectl get ingressclass
kubectl api-resources | grep -E 'applications|virtualmachines|virtualdisks|virtualimages|dexauthenticator|certificates'
kubectl auth can-i '*' '*' --all-namespaces
```

Ожидаемый результат:

- Kubernetes API доступен;
- есть подходящий StorageClass;
- есть IngressClass;
- DVP CRD доступны;
- DKP Dex/cert-manager CRD доступны, если включается self-service portal;
- оператор имеет права на создание namespaces, CRD-backed resources и RBAC.
