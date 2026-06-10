# 13. Ручное управление жизненным циклом стенда

## Цель

Показать досрочное удаление и операции с DVP VM без нарушения GitOps: портал
создаёт декларативное действие в Git, controller изменяет desired state, а
Argo CD применяет изменение или выполняет prune.

## Исходное состояние

- Application `practicum-demo` имеет `Synced/Healthy`;
- существует временный tenant environment с VM;
- пользователь входит через `selfservice-practicum.d8case.ru`;
- Victor входит через `vm-admin-practicum.d8case.ru`;
- golden builder VM не являются tenant environments и не отображаются Victor.

## Что меняем в Git

Портал создаёт объект:

```yaml
apiVersion: demo.practicum/v1
kind: EnvironmentAction
metadata:
  name: <environment>-delete-vm-<suffix>
spec:
  environment: <environment>
  action: delete-vm
  actor: <user-or-victor>
  actorEmail: <email>
  reason: <reason>
  requestedAt: <UTC timestamp>
```

Поддерживаются `delete-vm`, `delete-environment`, `start-vm`, `stop-vm` и
`restart-vm`.

## Пошаговое выполнение: пользователь

1. Откройте `https://selfservice-practicum.d8case.ru`.
2. Перейдите в `Мои стенды`.
3. Убедитесь, что чужие environments не отображаются.
4. Нажмите `Удалить VM` у собственного VM-профиля.
5. В первом диалоге проверьте Environment ID и предупреждение.
6. Подтвердите операцию второй кнопкой.
7. Наблюдайте `VMDeleting`.
8. После Argo CD prune убедитесь, что VM и VirtualDisk исчезли, а приложение
   осталось `1/1`.
9. Нажмите `Удалить стенд` и подтвердите.
10. Дождитесь `Deleting -> Cleaned`.

## Пошаговое выполнение: Victor

1. Откройте `https://vm-admin-practicum.d8case.ru`.
2. Войдите как `victor.melnikov.practicum@demo.local`.
3. Покажите KPI, фильтры и список tenant environments.
4. Убедитесь, что golden builder VM отсутствуют.
5. Выберите tenant VM и выполните `Stop`, указав обязательную причину.
6. Покажите `EnvironmentAction` и `VirtualMachineOperation` в дереве Argo CD.
7. После завершения выполните `Start`, затем `Restart`.
8. Для тестового стенда выполните `Удалить стенд`.
9. Проверьте audit: actor, reason, Git commit и outcome.

## Что показывать в Argo CD

- Application кратковременно становится `OutOfSync/Progressing`;
- появляется versioned `VirtualMachineOperation` для start/stop/restart;
- после завершения operation удаляется из desired state;
- delete VM/environment выполняется через prune;
- итоговое состояние — `Synced/Healthy`.

## Что показывать в AWX

- номер последнего post-config job;
- при удалении во время активного job controller запрашивает cancel;
- lifecycle actions не запускают повторный post-config без новой VM.

## Проверка через kubectl

```bash
kubectl get application -n practicum-tks practicum-demo
kubectl get deploy,svc,ingress,vd,vm,vmop -n practicum-tks \
  -l demo.practicum/environment=<environment-id>
```

## Ожидаемый результат

- пользователь управляет только собственными стендами;
- Victor управляет tenant environments всех пользователей;
- VM и диск удаляются вместе, приложение может быть сохранено;
- весь стенд удаляется только после изменения Git;
- namespace `practicum-tks`, golden images и platform workloads сохраняются;
- Git содержит полный audit действий.

## Rollback

Удалённый VirtualDisk восстановить нельзя. Для возврата VM создайте новый
EnvironmentRequest из активного golden image. Остановленную VM можно запустить
новым `start-vm` action.

## Пояснение для демонстратора

На этом шаге важно подчеркнуть, что портал не получил обходной путь к
Kubernetes. Даже административное действие Victor сначала становится
декларативным объектом в Git. Благодаря этому Argo CD не борется с оператором,
а исполняет новое desired state, а история пользователя, причины и результата
остаётся воспроизводимой и проверяемой.
