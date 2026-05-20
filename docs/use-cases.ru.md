# Use cases и сценарии применения

Документ описывает, что именно показывать аудитории на стенде Argo CD + AWX + Kubernetes + DVP.

## 1. GitOps-доставка Kubernetes-ресурсов

Инженер меняет манифесты в Git. Argo CD обнаруживает изменение и приводит кластер к описанному состоянию.

В локальном сценарии это:

- namespace `demo-os`;
- pod'ы `ol-node-1`, `ol-node-2`;
- Services для SSH.

В DKP/DVP сценарии это:

- namespace `demo-prod`;
- Deployment/Service/Ingress `demo-app`;
- RBAC, quotas, limit ranges;
- tenant `customer-a`.

Ценность: состояние инфраструктуры версионируется, проходит review и может быть восстановлено из Git.

## 2. GitOps-доставка DVP VM

Argo CD синхронизирует реальные DVP CRD:

- `VirtualImage demo-alpine-cloud`;
- `VirtualDisk postgres-vm-root`;
- `VirtualMachine postgres-vm`.

VM создана с минимальными ресурсами:

```text
1 core
coreFraction 5%
memory 512Mi
disk 256Mi
```

Ценность: виртуальная машина становится частью того же GitOps-контура, что и Kubernetes workload'ы.

## 3. Настройка ОС после создания ресурса

После того как Argo CD создал workload или VM, AWX запускает Ansible playbook и выполняет настройку внутри ОС.

В pod-only сценарии playbook:

- собирает facts;
- записывает `/etc/ansible-managed-by-awx`;
- устанавливает `htop`;
- выводит результат.

В DVP/VM сценарии подготовлены playbooks:

- `gitops/awx/playbooks/bootstrap-vm.yml`;
- `gitops/awx/playbooks/postgresql-tuning.yml`;
- `gitops/awx/playbooks/validate-vm.yml`.

Ценность: lifecycle Kubernetes/DVP-объектов и lifecycle ОС разделены, но связаны в единую операционную модель.

## 4. Configuration drift и self-healing

Администратор вручную меняет состояние в кластере, например:

```bash
kubectl scale deployment demo-app --replicas=10 -n demo-prod
```

Argo CD видит расхождение с Git и возвращает Deployment к значению из репозитория.

Ценность: Git остаётся источником истины, даже если кто-то изменил кластер вручную.

## 5. Rollback через Git

В Git попадает ошибка, например несуществующий image tag:

```yaml
app:
  image: nginx:broken-demo-tag
```

Kubernetes показывает `ImagePullBackOff`, Argo CD показывает `Progressing` или `Degraded`, затем команда делает:

```bash
git revert HEAD
git push
```

Ценность: восстановление выполняется тем же процессом, что и доставка, а история изменений сохраняется.

## 6. Self-service tenant onboarding

Platform team добавляет каталог:

```text
gitops/environments/prod/tenants/customer-a/
```

Argo CD создаёт:

- namespace;
- ResourceQuota;
- LimitRange;
- RBAC;
- starter workload;
- опциональный VM template.

Ценность: onboarding нового внутреннего заказчика становится повторяемым и стандартизированным.

## 7. Единый audit trail

Gitea хранит:

- Kubernetes manifests;
- DVP manifests;
- Ansible playbooks;
- сценарии демонстрации;
- документацию.

Argo CD показывает sync status и drift. AWX показывает историю job'ов, stdout и результат по host'ам.

Ценность: можно объяснить, что изменилось, каким инструментом и на каком уровне.

## 8. Управление golden image

Администратор указывает в Git URL исходного cloud image:

```text
gitops/environments/prod/golden-images/source-image.yaml
```

Argo CD применяет `VirtualImage`, DVP импортирует образ в кластер, затем создаётся builder disk и builder VM. AWX выполняет customization и validation, после чего публикуется новая версия golden image.

Ценность: golden image становится воспроизводимым артефактом с историей изменений, а не ручной загрузкой через UI.

## 9. Self-service создание временного стенда

Разработчик выбирает профиль стенда из approved catalog и создаёт Git request. Это можно сделать YAML-файлом или через web UI:

```bash
open self-service-ui/index.html
```

Профили:

- `app-only`;
- `app-with-vm`;
- `app-with-postgres-vm`.

После merge Argo CD создаёт generated manifests, а AWX выполняет post-configuration для профилей с VM.

Ценность: разработчик получает быстрый путь к стенду, а platform team сохраняет контроль через catalog, Git review, quotas, TTL и allow-list образов.

## Демонстрационный сценарий

### Подготовка

Проверить контекст:

```bash
kubectl config current-context
```

Для DKP ожидается:

```text
codex-api.d8.kir.lab
```

Проверить приложения:

```bash
kubectl get application -n argocd
```

Ожидаемо:

```text
ansible-os-pods   Synced   Healthy
demo-platform     Synced   Healthy
```

### Шаг 1. Показать Git как source of truth

Открыть Gitea:

```text
http://gitea-awx.d8.kir.lab
```

Показать файлы:

- `gitops/demo-manifests/os-nodes.yaml`;
- `gitops/environments/prod/dvp-postgres-vm.yaml`;
- `gitops/environments/prod/values.yaml`;
- `gitops/awx/playbooks/validate-vm.yml`;
- `scenarios/`.

Сообщение для аудитории: в одном Git-репозитории лежит декларативное состояние платформы, сценарии изменений и Ansible-автоматизация.

### Шаг 2. Показать Argo CD

Открыть:

```text
http://argocd-awx.d8.kir.lab
```

Показать Applications:

- `ansible-os-pods`;
- `demo-platform`.

Проверить из терминала:

```bash
kubectl get deploy,svc,ingress -n demo-prod
kubectl get vi,vd,vm -n demo-prod -o wide
```

Сообщение для аудитории: Argo CD синхронизирует и обычные Kubernetes-объекты, и DVP CRD.

### Шаг 3. Показать DVP VM

```bash
kubectl describe vm postgres-vm -n demo-prod
```

Что подчеркнуть:

- VM создана из Git;
- ресурсы минимальны для стенда;
- disk и image тоже управляются как Kubernetes CRD;
- VM находится в `Running`.

### Шаг 4. Показать AWX

Открыть:

```text
http://awx-demo.d8.kir.lab
```

Запустить pod-only job:

```bash
AWX_URL=http://awx-demo.d8.kir.lab ./scripts/run-demo-job.sh
```

Показать:

- `Gathering Facts`;
- marker `/etc/ansible-managed-by-awx`;
- recap `failed=0`.

Сообщение для аудитории: AWX не заменяет Argo CD. Он работает на другом уровне: внутри ОС.

### Шаг 5. Показать drift correction

```bash
kubectl scale deployment demo-app --replicas=10 -n demo-prod
argocd app get demo-platform
kubectl get deploy demo-app -n demo-prod
```

После self-heal replicas должны вернуться к значению из Git.

### Шаг 6. Показать rollback

Следовать сценарию:

```text
scenarios/06-broken-release-and-rollback.md
```

Главная мысль: ошибка и восстановление проходят через Git, а не через ручное исправление в кластере.

### Шаг 7. Показать tenant onboarding

```bash
kubectl get ns customer-a
kubectl get resourcequota,limitrange,rolebinding -n customer-a
kubectl get deploy,svc,ingress -n customer-a
```

Сообщение для аудитории: новый tenant появляется через каталог в Git, а не через ручной набор действий.

## Финальная формулировка

Argo CD отвечает за долгоживущее декларативное состояние Kubernetes/DVP-платформы. AWX отвечает за процедурную настройку внутри ОС. Вместе они дают воспроизводимый путь от Git commit до работающего и проверенного workload'а.
