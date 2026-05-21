# 09. Self-Service Environment Request

## Цель

Показать controlled self-service: разработчик создаёт запрос на временный стенд из заранее разрешённых профилей, а платформа через GitOps и AWX создаёт namespace, приложение, опциональную DVP VM, настройки и access info.

## Архитектурная идея

Self-service UI или YAML request не создают ресурсы напрямую. Они создают Git artifact:

```text
gitops/self-service/requests/<request-name>.yaml
```

После review/merge platform automation рендерит manifests в:

```text
gitops/self-service/generated/<request-name>/
```

Argo CD применяет generated manifests, а AWX выполняет post-configuration для профилей с VM.

## Исходное состояние

- Argo CD Application `demo-platform` синхронизирует `gitops/environments/prod`.
- `gitops/self-service/catalog/` содержит approved profiles.
- `self-service-ui/` содержит статическое web-приложение для генерации request YAML.
- Реальные секреты не хранятся в Git.

## Что меняем в Git

Разработчик создаёт request:

```text
gitops/self-service/requests/dev-alice-001.yaml
```

Пример:

```yaml
apiVersion: demo.platform/v1
kind: EnvironmentRequest
metadata:
  name: dev-alice-001
spec:
  owner: alice
  team: payments
  profile: app-with-vm
  ttl: 8h
  access:
    exposeIngress: true
    sshToVm: false
  software:
    appImage: nginx:1.27
  vm:
    image: alpine-base-3-23-v1
    imageKind: ClusterVirtualImage
```

## Профили

Approved catalog:

```text
gitops/self-service/catalog/app-only.yaml
gitops/self-service/catalog/app-with-vm.yaml
gitops/self-service/catalog/app-with-postgres-vm.yaml
```

Что показать аудитории:

> Разработчик не задаёт произвольные CPU/RAM/image. Он выбирает один из разрешённых профилей. Это controlled self-service, а не бесконтрольная выдача ресурсов.

## Web UI

Открыть локально:

```bash
open self-service-ui/index.html
```

Что показать:

- выбор owner/team/environment name;
- выбор profile;
- TTL;
- image из allow-list;
- YAML `EnvironmentRequest`;
- Git commands для branch/commit/push.

Что сказать:

> UI — это не второй control plane. Он помогает разработчику сформировать корректный GitOps-запрос. После этого всё равно остаются Git, review, merge, Argo CD и AWX.

## Пошаговое выполнение

### 1. Показать каталог профилей

Откройте Gitea:

```text
http://gitea-awx.d8.kir.lab
```

Файлы:

```text
gitops/self-service/catalog/app-only.yaml
gitops/self-service/catalog/app-with-vm.yaml
gitops/self-service/catalog/app-with-postgres-vm.yaml
```

### 2. Сгенерировать request через UI

```bash
open self-service-ui/index.html
```

Выберите:

- owner: `alice`;
- team: `payments`;
- environment: `dev-alice-001`;
- profile: `app-with-vm`;
- TTL: `8h`;
- app image: `nginx:1.27`;
- VM image: `alpine-base-3-23-v1`.
- VM image kind: `ClusterVirtualImage`, чтобы tenant namespace мог использовать утверждённый платформенный образ.
- VM в generated-примере запускается с `runPolicy: AlwaysOn`, но с минимальными ресурсами: `1` core, `coreFraction: 5%`, `512Mi`.

Скопируйте YAML.

### 3. Создать Git request

```bash
git checkout -b request/dev-alice-001
mkdir -p gitops/self-service/requests
$EDITOR gitops/self-service/requests/dev-alice-001.yaml
git add gitops/self-service/requests/dev-alice-001.yaml
git commit -m "Request self-service environment dev-alice-001"
git push origin request/dev-alice-001
git push dkp-gitea request/dev-alice-001
```

В production дальше создаётся PR. В демо можно показать уже подготовленный generated пример:

```text
gitops/self-service/generated/dev-alice-001/
```

### 4. Показать generated manifests

Файлы:

```text
namespace.yaml
quota.yaml
rbac.yaml
app.yaml
vm.yaml
access-secret.example.yaml
ACCESS.md
```

Что сказать:

> В production этот каталог должен генерироваться automation/CI/controller. В демо он добавлен заранее, чтобы показать результат обработки request.

### 5. Проверить Argo CD

```bash
kubectl get application -n argocd demo-platform
kubectl get ns dev-alice-001
kubectl get deploy,svc,ingress -n dev-alice-001
kubectl get vd,vm -n dev-alice-001 -o wide
```

### 6. Показать access info

Открыть:

```text
gitops/self-service/generated/dev-alice-001/ACCESS.md
```

Что сказать:

> Реальные креды не должны лежать в Git. Здесь только demo artifact и инструкция, где разработчик получает namespace, URL и способ доступа. В production это Vault, External Secrets, OIDC/RBAC или short-lived credentials.

### 7. AWX post-config

Для профиля `app-with-vm` AWX должен выполнить post-config:

- bootstrap VM;
- validation;
- при необходимости установку дополнительного ПО.

В текущем демо это можно показать как следующий автоматизируемый шаг через AWX API или Job Template.

## Альтернативный путь: GitOps/YAML без web UI

Этот вариант показывает, что web portal не является обязательной точкой входа. Разработчик может создать такую же заявку обычным YAML-файлом в Git.

### 1. Получить репозиторий

```bash
git clone https://github.com/kirka1206/ArgoAWXk8sDVPdemo.git
cd ArgoAWXk8sDVPdemo
git remote add dkp-gitea http://gitea-awx.d8.kir.lab/codex/demo.git || true
```

Что сказать:

> Для live-стенда важно пушить в Gitea, потому что Argo CD читает именно `http://gitea-awx.d8.kir.lab/codex/demo.git`.

### 2. Показать approved catalog

```bash
ls gitops/self-service/catalog
```

Ожидаемо:

```text
app-only.yaml
app-with-vm.yaml
app-with-postgres-vm.yaml
```

Что сказать:

> YAML-заявка не даёт разработчику произвольные ресурсы. Он всё равно выбирает approved profile.

### 3. Создать request YAML

```bash
cat > gitops/self-service/requests/dev-alice-yaml-demo.yaml <<'EOF'
apiVersion: demo.platform/v1
kind: EnvironmentRequest
metadata:
  name: dev-alice-yaml-demo
spec:
  owner: alice-koroleva
  email: alice.koroleva@demo.local
  groups:
    - payments-devs
  profile: app-with-vm
  purpose: demo
  ttl: 2h
  access:
    exposeIngress: true
    sshToVm: false
  software:
    appImage: nginx:1.27
  vm:
    image: alpine-base-3-23-v1
    imageKind: ClusterVirtualImage
EOF
```

Что объяснить:

- `metadata.name` станет именем заявки и будущего namespace;
- `owner`, `email`, `groups` фиксируют автора;
- `profile` выбирает approved template;
- `purpose` нужен для аудита и будущего cleanup/policy automation;
- `ttl` задаёт срок жизни;
- `appImage` и `vm.image` берутся из разрешённого набора.

### 4. Проверить diff и отправить в Git

```bash
git diff
git add gitops/self-service/requests/dev-alice-yaml-demo.yaml
git commit -m "Request self-service environment dev-alice-yaml-demo"
git push origin main
git push dkp-gitea main
```

Что сказать:

> В production вместо прямого push в `main` должен быть branch/PR, policy validation и approve/merge. Для демо допустим прямой push, чтобы быстро показать цепочку.

### 5. Generated manifests

Production-like automation должна создать:

```text
gitops/self-service/generated/dev-alice-yaml-demo/
```

В текущем стенде generated manifests создаёт portal/backend или демонстратор готовит их заранее.

Что сказать:

> Request - это входной объект. Argo CD применяет конкретные Kubernetes/DVP manifests из `generated/`. Следующий архитектурный шаг проекта - controller/CI, который автоматически превращает request в generated manifests.

### 6. Проверить Argo CD и ресурсы

```bash
kubectl get application -n argocd demo-platform
NS=dev-alice-yaml-demo
kubectl get ns $NS
kubectl get deploy,svc,ingress -n $NS
kubectl get vd,vm -n $NS
```

Ожидаемый результат для `app-with-vm`:

- `demo-platform` в состоянии `Synced/Healthy`;
- namespace `dev-alice-yaml-demo` создан;
- `demo-app` доступен;
- ingress создан;
- DVP `VirtualDisk` и `VirtualMachine` созданы.

### 7. Rollback

```bash
git rm gitops/self-service/requests/dev-alice-yaml-demo.yaml
git rm -r gitops/self-service/generated/dev-alice-yaml-demo
git commit -m "Remove self-service environment dev-alice-yaml-demo"
git push dkp-gitea main
```

Что сказать:

> Rollback и cleanup тоже проходят через Git. Это сохраняет историю и делает удаление таким же контролируемым, как создание.

## Что показывать в Argo CD

- Новый namespace `dev-alice-001`.
- Quota/RBAC.
- App Deployment/Service/Ingress.
- DVP VM resources, если профиль включает VM.

## Что показывать в AWX

- Что профиль определяет post-config playbooks.
- Что AWX не создаёт namespace/VM, а настраивает ОС после GitOps-создания.

## Проверка через kubectl

```bash
kubectl get ns dev-alice-001
kubectl get resourcequota,limitrange,rolebinding -n dev-alice-001
kubectl get deploy,svc,ingress -n dev-alice-001
kubectl get vd,vm -n dev-alice-001 -o wide
```

## Ожидаемый результат

- Request описан в Git.
- Generated manifests созданы из approved profile.
- Argo CD создал окружение.
- Разработчик получил namespace, endpoint и инструкцию по доступу.
- VM создаётся только для профилей, где она нужна.

## Rollback / Cleanup

Удаление временного стенда должно быть Git-driven:

```bash
git rm -r gitops/self-service/generated/dev-alice-001
git commit -m "Remove self-service environment dev-alice-001"
git push origin main
git push dkp-gitea main
```

Для production добавляется TTL cleanup controller/job.

## Пояснение для демонстратора

Self-service не означает, что разработчик получил cluster-admin. Он получил понятный интерфейс и каталог разрешённых профилей. Все изменения всё равно проходят через Git, а значит остаются review, история, rollback и политики. Web UI улучшает UX, но не заменяет GitOps.
