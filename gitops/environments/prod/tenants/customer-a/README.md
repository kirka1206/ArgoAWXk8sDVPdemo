# Tenant customer-a

Каталог демонстрирует self-service provisioning tenant'а через Git.

Добавление tenant-каталога моделирует согласованный platform-team процесс onboarding:

- namespace создаётся из Git;
- quota и limit range применяются из Git;
- RBAC стандартизирован;
- starter workload разворачивается автоматически;
- `vm.yaml` оставлен как пример VM-манифеста для tenant'а.

Файл `vm.yaml` не подключён в `kustomization.yaml`, чтобы случайно не создавать дополнительные VM на небольшом стенде. Перед применением адаптируйте его под фактический сценарий tenant'а и осознанно добавьте в kustomization.
