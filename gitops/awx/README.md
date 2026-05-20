# AWX post-configuration

Каталог содержит примеры для post-configuration после того, как Argo CD применил Kubernetes или DVP-ресурсы.

Важное правило: реальные AWX tokens нельзя хранить в Git.

Используйте `secrets/awx-token.example.yaml` только как пример структуры Secret. Для реального запуска замените dummy-значения безопасным способом вне репозитория.

Пример:

```bash
kubectl create secret generic awx-api-token \
  -n demo-prod \
  --from-literal=url=https://awx.example.local \
  --from-literal=token=demo-token-replace-me
```

Перед использованием замените:

- `https://awx.example.local`;
- `demo-token-replace-me`;
- `replace-with-template-id` в `hooks/awx-postsync-job.yaml`.

Playbooks:

- `playbooks/bootstrap-vm.yml` - базовая настройка ОС;
- `playbooks/postgresql-tuning.yml` - пример настройки PostgreSQL;
- `playbooks/validate-vm.yml` - проверка доступности, сервисов и портов.
