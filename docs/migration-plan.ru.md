# Детальный план переноса демо на новый DKP/DVP стенд

Документ описывает перенос текущего демо Argo CD + AWX + Gitea + DKP/DVP + self-service portal на новый стенд.

Перед началом прочитайте:

```text
docs/prerequisites.ru.md
docs/STATUS.md
docs/NEXT_STEPS.md
```

## 0. Зафиксировать исходное состояние

На текущем стенде:

```bash
kubectl config current-context
kubectl get application -n argocd -o wide
kubectl get ns
kubectl get vi,cvi,vd,vm -A -o wide
git status --short --branch
git log --oneline -5
```

Ожидаемо для актуального состояния проекта:

```text
ansible-os-pods   Synced   Healthy
demo-platform     Synced   Healthy
```

Текущая живая ревизия после последних исправлений:

```text
13e30f798f30d77877bc6206659d7abe3fe397b1
```

Рекомендуется создать тег или отдельную ветку перед переносом:

```bash
git tag -a migration-ready-$(date +%Y%m%d) -m "Migration-ready demo state"
git push origin --tags
git push dkp-gitea --tags
```

## 1. Выбрать параметры нового стенда

До изменения файлов заполнить таблицу:

| Параметр | Текущий стенд | Новый стенд |
| --- | --- | --- |
| kube-context | `codex-api.d8.kir.lab` | `<target-context>` |
| Базовый домен | `d8.kir.lab` | `<target-domain>` |
| Ingress IP | `10.77.77.208` | `<target-ingress-ip>` |
| Gitea host | `gitea-awx.d8.kir.lab` | `gitea-awx.<target-domain>` |
| Argo CD host | `argocd-awx.d8.kir.lab` | `argocd-awx.<target-domain>` |
| AWX host | `awx-demo.d8.kir.lab` | `awx-demo.<target-domain>` |
| Portal host | `selfservice-awx.d8.kir.lab` | `selfservice-awx.<target-domain>` |
| StorageClass | `k8nfs` | `<target-storage-class>` |
| DVP VM class | `generic` | `<target-vm-class>` |
| Gitea owner/repo | `codex/demo` | `codex/demo` или новое значение |

Решение: если хотите минимизировать правки, на новом стенде сохранить `codex/demo`, `k8nfs`, `generic` и hostnames по тому же шаблону, поменяв только домен.

## 2. Подготовить целевой DKP/DVP кластер

Проверить доступ:

```bash
kubectl config use-context <target-context>
kubectl get nodes -o wide
kubectl get storageclass
kubectl get ingressclass
```

Проверить DVP:

```bash
kubectl api-resources | grep -E 'virtualmachines|virtualdisks|virtualimages|clustervirtualimages'
kubectl get virtualmachineclass
```

Проверить DKP/Dex/certificates:

```bash
kubectl api-resources | grep -E 'dexauthenticator|certificates|users|groups'
```

Если чего-то нет, сначала включить нужные DKP modules или подготовить альтернативный вариант:

- без self-service portal DexAuthenticator;
- без DVP сценариев;
- с другим IngressClass;
- с другим StorageClass.

## 3. Подготовить DNS или `/etc/hosts`

Для временного переноса можно использовать `/etc/hosts`:

```text
<target-ingress-ip> gitea-awx.<target-domain>
<target-ingress-ip> argocd-awx.<target-domain>
<target-ingress-ip> awx-demo.<target-domain>
<target-ingress-ip> selfservice-awx.<target-domain>
```

Для self-service apps желательно wildcard DNS:

```text
*.<target-domain> -> <target-ingress-ip>
```

Если wildcard невозможен, добавлять записи для создаваемых стендов:

```text
<target-ingress-ip> dev-alice-koroleva-demo-c3aa.<target-domain>
<target-ingress-ip> dev-alice-koroleva-feature-f72b.<target-domain>
<target-ingress-ip> dev-alice-koroleva-feature-8c3e.<target-domain>
```

## 4. Склонировать проект и создать migration branch

На рабочей машине:

```bash
git clone git@github.com:kirka1206/ArgoAWXk8sDVPdemo.git
cd ArgoAWXk8sDVPdemo
git checkout main
git pull origin main
git checkout -b migrate/<target-stand-name>
```

Если переносите именно текущее состояние из Gitea стенда, добавьте remote и подтяните его:

```bash
git remote add source-dkp-gitea http://gitea-awx.d8.kir.lab/codex/demo.git || true
git fetch source-dkp-gitea main
git merge --no-edit source-dkp-gitea/main
```

## 5. Заменить параметры стенда

Найти текущие hardcoded значения:

```bash
rg -n 'd8\\.kir\\.lab|codex-api\\.d8\\.kir\\.lab|10\\.77\\.77\\.208|k8nfs|virtualMachineClassName: generic' .
```

Обновить минимум:

```text
scripts/deploy-dkp.sh
manifests/dkp/ingresses.yaml
gitops/self-service/portal/ingress.yaml
gitops/self-service/portal/certificate.yaml
gitops/self-service/portal/dex-authenticator.yaml
gitops/self-service/portal/deployment.yaml
gitops/environments/prod/dvp-postgres-vm.yaml
gitops/environments/prod/golden-images/builder-vm.yaml
gitops/self-service/generated/*/app.yaml
gitops/self-service/generated/*/vm.yaml
```

Если меняется owner/repo Gitea, обновить:

```text
manifests/argocd/application-demo.yaml
manifests/argocd/application-demo-platform.yaml
gitops/self-service/portal/deployment.yaml
```

Если меняется StorageClass, заменить:

```bash
rg -n 'k8nfs' .
```

Если меняется домен self-service apps, заменить:

```bash
rg -n 'd8\\.kir\\.lab' gitops/self-service manifests/dkp docs README.md README.ru.md
```

## 6. Решить, переносить ли текущие generated self-service стенды

В текущем проекте есть live-generated заявки:

```text
gitops/self-service/requests/dev-alice-koroleva-demo-c3aa.yaml
gitops/self-service/requests/dev-alice-koroleva-feature-f72b.yaml
gitops/self-service/requests/dev-alice-koroleva-feature-8c3e.yaml
```

Они демонстрационно полезны, потому что показывают результат работы portal backend.

Есть два варианта.

### Вариант A. Перенести как есть

Оставить `requests/` и `generated/`. На новом стенде Argo CD создаст эти namespace и, для профилей с VM, DVP VM.

Плюс: быстро видно готовый результат.

Минус: это уже созданные demo-заявки Alice, их TTL логически истек или скоро истечет. В текущей реализации TTL cleanup automation еще не реализован.

### Вариант B. Очистить перед переносом

Удалить generated-заявки из Git:

```bash
git rm -r gitops/self-service/requests/dev-alice-koroleva-*.yaml
git rm -r gitops/self-service/generated/dev-alice-koroleva-*
```

Оставить валидный пустой top-level kustomization:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources: []
```

Плюс: новый стенд стартует чистым.

Минус: результат self-service нужно будет создать заново через portal.

## 7. Проверить рендер manifests до установки

Локально:

```bash
kubectl kustomize gitops/environments/prod >/tmp/demo-platform.yaml
kubectl kustomize gitops/demo-manifests >/tmp/ansible-os-pods.yaml
```

Если установлен `kustomize`:

```bash
kustomize build gitops/environments/prod >/tmp/demo-platform.yaml
```

Проверить, что нет старого домена:

```bash
rg -n 'd8\\.kir\\.lab|10\\.77\\.77\\.208|codex-api\\.d8\\.kir\\.lab' .
```

Допустимо оставить старые значения только в исторической документации, если она явно помечена как пример исходного стенда.

## 8. Подготовить и отправить Git

Закоммитить изменения migration branch:

```bash
git status --short
git add .
git commit -m "Adapt demo for <target-stand-name>"
git push origin migrate/<target-stand-name>
```

Дальше либо merge в `main`, либо отдельная ветка для проверки.

Для live Argo CD в новом стенде важно, чтобы проект попал во внутренний Gitea этого стенда. Bootstrap делает это автоматически через `local-gitea`.

## 9. Запустить базовый bootstrap на новом стенде

Выполнить:

```bash
CONTEXT=<target-context> \
GITEA_HOST=gitea-awx.<target-domain> \
ARGOCD_HOST=argocd-awx.<target-domain> \
AWX_HOST=awx-demo.<target-domain> \
./scripts/deploy-dkp.sh
```

Скрипт:

1. проверит kube-context;
2. установит Argo CD;
3. установит Gitea;
4. создаст пользователя `codex` и repo `demo`;
5. отправит текущий проект во внутренний Gitea;
6. создаст Argo CD Application `ansible-os-pods`;
7. установит AWX operator и AWX;
8. создаст базовые AWX объекты для pod-only сценария;
9. создаст Ingress для Gitea, Argo CD и AWX.

Проверка:

```bash
kubectl get pods -n argocd
kubectl get pods -n gitea
kubectl get pods -n awx
kubectl get application -n argocd ansible-os-pods
```

## 10. Применить расширенный DVP Application

После bootstrap:

```bash
kubectl apply -f manifests/argocd/application-demo-platform.yaml
kubectl annotate application -n argocd demo-platform argocd.argoproj.io/refresh=hard --overwrite
```

Ждать:

```bash
kubectl get application -n argocd demo-platform -w
```

Проверить:

```bash
kubectl get deploy,svc,ingress -n demo-prod
kubectl get vi,cvi,vd,vm -A -o wide
kubectl get ns customer-a
```

Ожидаемый минимум:

- `demo-platform` в `Synced/Healthy`;
- `demo-prod/demo-app` доступен;
- `VirtualImage/demo-alpine-cloud` в `Ready`;
- `VirtualDisk/postgres-vm-root` в `Ready`;
- `VirtualMachine/postgres-vm` в `Running`;
- `ClusterVirtualImage/alpine-base-3-23-v1` в `Ready`.

## 11. Настроить DNS и проверить UI

Проверить:

```bash
curl -I http://gitea-awx.<target-domain>
curl -I http://argocd-awx.<target-domain>
curl -I http://awx-demo.<target-domain>
```

Открыть в браузере:

```text
http://gitea-awx.<target-domain>
http://argocd-awx.<target-domain>
http://awx-demo.<target-domain>
```

Argo CD admin password:

```bash
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 -d; echo
```

AWX admin password:

```bash
kubectl -n awx get secret awx-demo-admin-password \
  -o jsonpath='{.data.password}' | base64 -d; echo
```

## 12. Подготовить self-service portal

Создать Secret для Gitea API:

```bash
kubectl create namespace self-service-portal --dry-run=client -o yaml | kubectl apply -f -
kubectl -n self-service-portal create secret generic self-service-portal-gitea \
  --from-literal=username=codex \
  --from-literal=password='<gitea-password>' \
  --dry-run=client -o yaml | kubectl apply -f -
```

Создать demo users/groups, если они нужны:

```bash
cp gitops/self-service/portal/dex-demo-users.example.yaml /tmp/dex-demo-users.yaml
# заменить replace-with-bcrypt-hash на реальные bcrypt-хэши
kubectl apply -f /tmp/dex-demo-users.yaml
```

Проверить portal:

```bash
kubectl get deploy,svc,ingress,dexauthenticator,certificate -n self-service-portal
curl -kI https://selfservice-awx.<target-domain>
```

Открыть:

```text
https://selfservice-awx.<target-domain>
```

## 13. Настроить AWX для DVP VM

Bootstrap создает pod-only AWX job template. Для DVP VM добавить:

1. Inventory `DVP VMs`.
2. Credential `dvp-vm-ssh`.
3. Host `postgres-vm` с актуальным IP:

```bash
kubectl get vm postgres-vm -n demo-prod -o wide
```

4. Job Template `Bootstrap DVP VM`:

```text
Inventory: DVP VMs
Project: Gitea demo repo
Playbook: gitops/awx/playbooks/bootstrap-vm.yml
Credential: dvp-vm-ssh
```

5. Job Template `Validate DVP VM`:

```text
Inventory: DVP VMs
Project: Gitea demo repo
Playbook: gitops/awx/playbooks/validate-vm.yml
Credential: dvp-vm-ssh
```

Проверка доступа из кластера:

```bash
VM_IP=$(kubectl get vm postgres-vm -n demo-prod -o jsonpath='{.status.ipAddress}')
kubectl run -n demo-prod netcheck --rm -i --restart=Never \
  --image=busybox:1.36 --timeout=20s -- \
  nc -vz -w 3 "$VM_IP" 22
```

## 14. Настроить golden image сценарий

Проверить source image:

```bash
kubectl get vi alpine-base-3-23-v1 -n demo-prod
kubectl get cvi alpine-base-3-23-v1
kubectl get vd,vm -n demo-prod | grep golden
```

Для запуска builder VM:

```bash
kubectl patch vm golden-builder-vm -n demo-prod --type merge -p '{"spec":{"runPolicy":"AlwaysOn"}}'
```

После получения IP добавить host в AWX inventory `Golden Image Builders`:

```bash
kubectl get vm golden-builder-vm -n demo-prod -o wide
```

Создать в AWX:

```text
Job Template: Prepare Golden Image
Inventory: Golden Image Builders
Project: Gitea demo repo
Playbook: gitops/awx/playbooks/prepare-golden-image.yml
Credential: dvp-vm-ssh

Job Template: Validate Golden Image
Inventory: Golden Image Builders
Project: Gitea demo repo
Playbook: gitops/awx/playbooks/validate-golden-image.yml
Credential: dvp-vm-ssh
```

Публикацию новой версии golden image выполнять через новый versioned manifest, не через перезапись существующего provisioned disk.

## 15. Проверить демонстрационные сценарии

Минимальный smoke test:

```bash
kubectl get application -n argocd
kubectl get pods -n demo-os
kubectl get deploy,svc,ingress -n demo-prod
kubectl get vi,cvi,vd,vm -A -o wide
AWX_URL=http://awx-demo.<target-domain> ./scripts/run-demo-job.sh
```

Self-service portal smoke test:

1. Войти как demo user через Dex.
2. Создать `app-only` стенд.
3. Дождаться commit в Gitea.
4. Проверить `demo-platform` в Argo CD.
5. Проверить namespace:

```bash
kubectl get ns | grep dev-
kubectl get deploy,svc,ingress -n <generated-namespace>
```

VM profile smoke test:

```bash
kubectl get vd,vm -n <generated-namespace> -o wide
```

## 16. Критерии приемки переноса

Перенос считается успешным, если:

- Gitea UI открывается по новому host;
- Argo CD UI открывается по новому host;
- AWX UI открывается по новому host;
- `ansible-os-pods` в `Synced/Healthy`;
- `demo-platform` в `Synced/Healthy`;
- `demo-os` pod-only сценарий проходит через AWX;
- `demo-prod/postgres-vm` в `Running`;
- `ClusterVirtualImage/alpine-base-3-23-v1` в `Ready`;
- self-service portal открывается через HTTPS и Dex;
- portal может создать request в Gitea;
- Argo CD применяет generated namespace;
- для VM-профиля DVP создает `VirtualDisk` и `VirtualMachine`.

## 17. Rollback и очистка

Если перенос не удался до применения `demo-platform`:

```bash
./scripts/destroy.sh
```

Если `demo-platform` уже применен:

```bash
kubectl delete application demo-platform -n argocd --cascade=foreground
kubectl delete ns demo-prod customer-a self-service-portal --ignore-not-found
```

Для generated self-service namespaces:

```bash
kubectl get ns | grep '^dev-'
kubectl delete ns <generated-namespace>
```

GitOps-правильный rollback:

```bash
git revert HEAD
git push origin main
git push dkp-gitea main
kubectl annotate application -n argocd demo-platform argocd.argoproj.io/refresh=hard --overwrite
```

## 18. Типовые проблемы при переносе

### Argo CD не может собрать manifests

Проверить:

```bash
kubectl kustomize gitops/environments/prod
kubectl describe application -n argocd demo-platform
```

Частый случай для self-service:

```yaml
resources: []
  - some-env
```

Это невалидно. Должно быть:

```yaml
resources:
  - some-env
```

или пустой список:

```yaml
resources: []
```

### DVP запрещает менять `VirtualDisk.dataSource`

Если диск уже provisioned, DVP не разрешает менять источник. Используйте новый диск, restore/recreate flow или scoped `ignoreDifferences`, как сделано для `demo-prod/postgres-vm-root`.

### Portal пишет в Git, но Argo CD ничего не создает

Проверить:

```bash
kubectl logs -n self-service-portal deploy/self-service-portal
kubectl get application demo-platform -n argocd
git fetch dkp-gitea main
git log --oneline dkp-gitea/main -5
```

Причины:

- portal пишет не в тот owner/repo/branch;
- Secret `self-service-portal-gitea` неверный;
- Argo CD смотрит на другой repoURL;
- generated `kustomization.yaml` не включает новый каталог.

### Dex login возвращает 403

Проверить:

```bash
kubectl get dexauthenticator -n self-service-portal
kubectl get users.deckhouse.io
kubectl get groups.deckhouse.io
kubectl logs -n self-service-portal deploy/self-service-portal
```

Пользователь должен входить в одну из allowed groups:

```text
payments-devs
analytics-devs
qa-devs
```

### AWX не подключается к VM

Проверить IP и SSH:

```bash
kubectl get vm -A -o wide
kubectl run -n demo-prod netcheck --rm -i --restart=Never \
  --image=busybox:1.36 --timeout=20s -- \
  nc -vz -w 3 <vm-ip> 22
```

Проверить AWX credential и host variables.
