# 05. AWX Post-Configuration

## Цель

Показать, зачем нужен AWX вместе с ArgoCD.

## Исходное состояние

- ArgoCD создал или изменил Kubernetes/DVP-ресурсы.
- VM `postgres-vm` доступна для Ansible по SSH.
- AWX inventory содержит `postgres-vm`.
- AWX token хранится в Kubernetes Secret, а не в Git.

## Что меняем в Git

Добавляем или обновляем:

- `gitops/awx/playbooks/bootstrap-vm.yml`
- `gitops/awx/playbooks/postgresql-tuning.yml`
- `gitops/awx/playbooks/validate-vm.yml`
- `gitops/awx/hooks/awx-postsync-job.yaml`
- `gitops/awx/secrets/awx-token.example.yaml`

## Пошаговое выполнение

```bash
kubectl get vm postgres-vm -n demo-prod
kubectl get job -n demo-prod
kubectl logs job/awx-postsync-launch -n demo-prod
ansible-playbook gitops/awx/playbooks/validate-vm.yml
```

В AWX UI запустите Job Template вручную или покажите запуск через PostSync hook.

## Что показывать в ArgoCD

- PostSync hook `awx-postsync-launch`.
- Sync wave `4`.
- Что hook запускается после применения инфраструктуры.

## Что показывать в AWX

- Inventory с `postgres-vm`.
- Job Template для bootstrap/postgresql tuning/validation.
- Stdout playbooks.
- Успешный финальный статус job.

## Проверка через kubectl

```bash
kubectl get job awx-postsync-launch -n demo-prod
kubectl logs job/awx-postsync-launch -n demo-prod
```

## Ожидаемый результат

- AWX Job завершился успешно.
- ОС внутри VM настроена.
- PostgreSQL параметры применены.
- Validation показал успешный статус.

## Rollback

```bash
git revert HEAD
git push
argocd app get demo-platform
```

Если AWX job уже изменил ОС, выполните отдельный remediation playbook или повторите post-config с предыдущими значениями.

## Пояснение для демонстратора

Здесь важно показать границу между декларативным и процедурным управлением. ArgoCD хорошо создаёт Kubernetes/DVP-объекты, но не должен превращаться в инструмент настройки ОС. AWX закрывает этот слой: пакеты, сервисы, PostgreSQL tuning и validation внутри гостевой системы.
