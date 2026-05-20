# 07. Self-Service Tenant

## Цель

Показать self-service provisioning нового tenant через добавление каталога в Git.

## Исходное состояние

- Platform team поддерживает tenant template.
- ArgoCD Application `demo-platform` синхронизирует prod-окружение.
- Новый внутренний заказчик называется `customer-a`.

## Что меняем в Git

Добавляем каталог:

```text
gitops/environments/prod/tenants/customer-a/
```

Файлы:

- `namespace.yaml`
- `resourcequota.yaml`
- `limitrange.yaml`
- `rbac.yaml`
- `app.yaml`
- `vm.yaml`
- `README.md`

## Пошаговое выполнение

```bash
cp -r gitops/environments/prod/tenants/template gitops/environments/prod/tenants/customer-a
git add gitops/environments/prod/tenants/customer-a
git commit -m "Add customer-a tenant"
git push
argocd app get demo-platform
kubectl get ns customer-a
kubectl get resourcequota -n customer-a
kubectl get limitrange -n customer-a
kubectl get rolebinding -n customer-a
kubectl get deploy,svc,ingress -n customer-a
```

Если tenant уже добавлен в репозиторий, используйте существующий каталог как демонстрационный результат.

## Что показывать в ArgoCD

- Новые ресурсы tenant в tree.
- Sync waves для namespace/RBAC/quota перед workload.
- Что platform team контролирует шаблон через Git.

## Что показывать в AWX

При необходимости AWX может добавить tenant VM в inventory и выполнить bootstrap. В базовом сценарии достаточно показать, что post-config слой подключается тем же способом, что в сценарии 05.

## Проверка через kubectl

```bash
kubectl get ns customer-a
kubectl get resourcequota -n customer-a
kubectl get limitrange -n customer-a
kubectl get rolebinding -n customer-a
kubectl get deploy,svc,ingress -n customer-a
```

## Ожидаемый результат

- Namespace `customer-a` создан.
- Quota и LimitRange применены.
- RBAC настроен.
- Demo workload создан.
- Tenant подключён через GitOps.

## Rollback

```bash
git revert HEAD
git push
argocd app get demo-platform
```

Если включен `prune: true`, ArgoCD удалит ресурсы tenant, которых больше нет в Git.

## Пояснение для демонстратора

Этот сценарий хорошо работает для presale: новый tenant появляется не через набор ручных действий в кластере, а через стандартизированный каталог в Git. Platform team сохраняет контроль над шаблоном, а onboarding становится повторяемым и проверяемым.
