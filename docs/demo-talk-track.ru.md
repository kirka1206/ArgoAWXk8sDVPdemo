# Короткий сценарий демонстрации

Шпаргалка для живого показа стенда.

## 0. Вступление

Цель стенда: показать, как GitOps и AWX работают вместе.

Сразу зафиксировать границу:

- Argo CD не управляет ОС по SSH.
- Argo CD управляет Kubernetes/DVP-ресурсами из Git.
- AWX/Ansible управляет настройкой внутри ОС после создания workload'а или VM.

В локальном сценарии используются Linux pod'ы. В DKP/DVP сценарии есть настоящая минимальная VM `postgres-vm`.

## 1. Git: единый источник истины

Открыть:

```text
http://gitea-awx.d8.kir.lab
```

Показать репозиторий `codex/demo`.

Файлы для показа:

- `gitops/environments/prod/dvp-postgres-vm.yaml`;
- `gitops/environments/prod/demo-app.yaml`;
- `gitops/environments/prod/tenants/customer-a/`;
- `gitops/awx/playbooks/`;
- `scenarios/`.

Что сказать:

> Здесь лежит источник истины для демо: Kubernetes manifests, DVP manifests, Ansible playbooks и сценарии изменений. Все изменения можно обсуждать, ревьюить и откатывать через Git.

## 2. Argo CD: доставка ресурсов

Открыть:

```text
http://argocd-awx.d8.kir.lab
```

Показать:

- Application `ansible-os-pods`;
- Application `demo-platform`;
- состояние `Synced/Healthy`;
- дерево ресурсов.

Команды:

```bash
kubectl get application -n argocd
kubectl get deploy,svc,ingress -n demo-prod
```

Что сказать:

> Argo CD сравнивает кластер с Git и приводит его к описанному состоянию. Он не выполняет shell-команды внутри ОС, а синхронизирует Kubernetes API и DVP CRD.

## 3. DVP VM: инфраструктура из Git

Команда:

```bash
kubectl get vi,vd,vm -n demo-prod -o wide
```

Ожидаемо:

```text
demo-alpine-cloud   Ready
postgres-vm-root    Ready   256Mi
postgres-vm         Running 1 core 5% 512Mi
```

Что сказать:

> Это настоящая DVP VM, но с минимальными ресурсами для стенда. Image, disk и VM описаны в Git и синхронизированы Argo CD.

## 4. AWX: настройка ОС

Открыть:

```text
http://awx-demo.d8.kir.lab
```

Запустить:

```bash
AWX_URL=http://awx-demo.d8.kir.lab ./scripts/run-demo-job.sh
```

Показать:

- stdout job;
- `Gathering Facts`;
- marker `/etc/ansible-managed-by-awx`;
- recap `failed=0`.

Что сказать:

> Этот файл появился не из Kubernetes manifest. Его создал AWX через Ansible внутри ОС. Так мы разделяем platform state и OS configuration.

## 5. Drift correction

Команды:

```bash
kubectl get deploy demo-app -n demo-prod
kubectl scale deployment demo-app --replicas=10 -n demo-prod
argocd app get demo-platform
kubectl get deploy demo-app -n demo-prod
```

Что сказать:

> Ручное изменение в кластере является drift. При включенном self-heal Argo CD возвращает состояние к Git.

## 6. Rollback

Показать сценарий:

```text
scenarios/06-broken-release-and-rollback.md
```

Что сказать:

> Rollback не требует ручного исправления в кластере. Мы откатываем Git commit, и Argo CD приводит кластер к предыдущему рабочему состоянию.

## 7. Tenant onboarding

Команды:

```bash
kubectl get ns customer-a
kubectl get resourcequota,limitrange,rolebinding -n customer-a
kubectl get deploy,svc,ingress -n customer-a
```

Что сказать:

> Новый tenant создаётся добавлением каталога в Git. Platform team контролирует шаблон, а onboarding становится повторяемым.

## 8. Финал

Если аудитория спрашивает про self-service для разработчиков, покажите:

```text
self-service-ui/index.html
gitops/self-service/catalog/
gitops/self-service/requests/dev-alice-001.yaml
gitops/self-service/generated/dev-alice-001/
scenarios/09-self-service-environment-request.md
```

Что сказать:

> Разработчик не получает прямой доступ к кластеру. Он выбирает approved profile в web UI или YAML request. UI генерирует GitOps request, дальше работают review, Argo CD и AWX. Это self-service без обхода governance.

Если аудитория спрашивает про golden image, покажите:

```text
gitops/environments/prod/golden-images/source-image.yaml
scenarios/08-golden-image-management.md
```

Что сказать:

> В production часто нужно управлять золотыми образами. В этом стенде администратор задаёт URL исходного image в Git. Argo CD создаёт DVP `VirtualImage`, DVP импортирует образ, AWX готовит builder VM, а новая версия golden image публикуется как отдельный immutable artifact.

Короткий порядок показа:

1. Gitea: `gitops/environments/prod/golden-images/source-image.yaml` — URL исходного image.
2. Argo CD: `demo-platform` — `VirtualImage`, `VirtualDisk`, `VirtualMachine`.
3. Terminal: `kubectl get vi,vd,vm -n demo-prod -o wide`.
4. AWX: `prepare-golden-image.yml` и `validate-golden-image.yml`.
5. Gitea: `publish-golden-image.example.yaml` — публикация версии после validation.
6. Объяснить rollback: переключение обратно на предыдущий image reference через Git.

Финальная формулировка:

> Argo CD отвечает за декларативное состояние платформы. AWX отвечает за операционную настройку ОС. DVP VM, Kubernetes workload'ы и tenant'ы управляются из Git, а post-configuration и validation выполняются через AWX.
