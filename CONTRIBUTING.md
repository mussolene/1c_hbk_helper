# Руководство по внесению вклада

## Conventional Commits

Проект использует [Conventional Commits](https://www.conventionalcommits.org/) для единообразных сообщений коммитов. Это позволяет автоматически генерировать changelog и release notes из истории Git.

### Формат

```
<type>[(scope)]: <description>

[optional body]

[optional footer(s)]
```

### Типы (type)

| Тип      | Описание                              |
|----------|----------------------------------------|
| `feat`   | Новая функциональность                 |
| `fix`    | Исправление бага                       |
| `docs`   | Изменения в документации               |
| `style`  | Форматирование (не меняет логику)      |
| `refactor` | Рефакторинг кода                     |
| `perf`   | Улучшение производительности           |
| `test`   | Добавление или правка тестов           |
| `build`  | Изменения сборки (Docker, зависимости) |
| `ci`     | Изменения CI/CD                        |
| `chore`  | Прочие изменения                       |

### Примеры

```
feat(mcp): add get_form_metadata tool
fix(ingest): handle empty cache file
docs: update README installation section
ci: add Python 3.14 to test matrix
chore: ruff format
```

### Валидация

Сообщения коммитов проверяются в CI при создании Pull Request (workflow `Lint Commits`). Коммиты должны соответствовать формату, иначе проверка не пройдёт.

### Release notes

При пуше тега (`v*`) workflow Release генерирует changelog из conventional commits с помощью [git-cliff](https://git-cliff.org/) и использует его как описание GitHub Release.

### Версионирование

Версия задаётся **только** в `pyproject.toml` (поле `[project] version`). Модуль `onec_help.__version__` подхватывает её из метаданных установленного пакета. При релизе: обновить версию в `pyproject.toml`, закоммитить, создать тег `vX.Y.Z`, запушить.
