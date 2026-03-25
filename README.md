# MVP de Ranqueamento de Inscricoes

MVP em Python para automatizar a avaliacao e o ranqueamento de inscricoes de empresas em jornadas de exportacao da ApexBrasil.

## O que este projeto faz

- Le CSV ou XLSX exportado do Microsoft Dynamics.
- Padroniza as inscricoes em um modelo unico.
- Aplica criterios eliminatorios e classificatorios definidos em configuracao JSON.
- Calcula nota total, corte minimo e desempate.
- Faz verificacoes automaticas de CNPJ, site/rede social, idioma estrangeiro e cartao CNPJ.
- Marca sugestoes que exigem revisao humana.
- Exporta um arquivo Excel com quatro abas:
  - `inscricoes_brutas`
  - `avaliacao_por_criterio`
  - `ranking_final`
  - `pendencias_revisao`

## Estrutura

```text
.
├── config/
├── models/
├── services/
├── tests/
├── main.py
└── requirements.txt
```

## Formato esperado da entrada

Para o MVP, o sistema normaliza os nomes das colunas para `snake_case` e tenta identificar alguns campos-base, como:

- `inscricao_id`
- `empresa_nome`
- `cnpj`
- `data_submissao`

Os demais campos ficam disponiveis para as regras com o nome normalizado da coluna de entrada.

Exemplo:

- `Aceite Regulamento` vira `aceite_regulamento`
- `Anos Experiencia Exportacao` vira `anos_experiencia_exportacao`

Para a Jornada Exportadora Autopartes, o projeto agora aceita tambem a exportacao crua do Dynamics, mesmo quando a aba nao se chama `Ranqueamento`.

## Verificacao automatica e IA

O pipeline foi ampliado com uma etapa de enriquecimento antes das regras do edital. Nela, o sistema pode:

- validar estruturalmente o CNPJ pelos digitos verificadores;
- comparar o CNPJ com o nome da empresa em fonte oficial configurada;
- derivar pendencia financeira a partir do status vindo do CRM;
- verificar website ou rede social informada;
- detectar se o canal apresenta indicios de ingles e/ou espanhol;
- tentar ler o cartao CNPJ e confrontar CNPJ e razao social.

Sem chave de IA, o sistema usa heuristicas deterministicas e marca revisao humana quando a evidencia fica inconclusiva.

Com `OPENAI_API_KEY`, ele tambem pode usar o modelo configurado em `verificacoes_automaticas.openai` para:

- desempatar casos ambiguos de site/rede social;
- confirmar idioma e aderencia do canal internacional;
- tentar interpretar cartao CNPJ em PDF ou imagem quando a extracao de texto nao basta.

### Consulta oficial de CNPJ

O projeto agora suporta uma segunda camada de verificacao para conferir se o CNPJ informado corresponde mesmo a razao social ou ao nome fantasia da empresa.

Essa camada e configuravel e pode usar:

- um dataset local oficial ou saneado em `CSV`, `XLSX` ou `JSON`;
- uma API HTTP configurada pela equipe, como wrapper interno ou integracao oficial autorizada.

Exemplo de ativacao por dataset local:

```bash
export CNPJ_PUBLIC_DATASET_PATH="/caminho/para/cnpj_publico.csv"
```

No regulamento, a secao `verificacoes_automaticas.cnpj_consulta_oficial` pode apontar para esse arquivo e definir as colunas do cadastro oficial.

Quando a fonte oficial estiver habilitada, o sistema passa a preencher campos como:

- `cnpj_empresa_confere_cadastro_oficial`
- `cnpj_empresa_confere_cadastro_oficial_justificativa`
- `cnpj_cadastro_oficial_razao_social`
- `cnpj_cadastro_oficial_nome_fantasia`
- `cnpj_cadastro_oficial_situacao_cadastral`

## Como executar

No seu ambiente atual, o caminho mais simples e estavel e usar os scripts do projeto, que ja configuram `PYTHONPATH=.vendor` e evitam depender de uma virtualenv local.

### CLI

```bash
./run.sh \
  --entrada /caminho/para/inscricoes.csv \
  --regulamento config/regulamento_exemplo.json \
  --saida ./saida/ranking_apex.xlsx
```

### Interface web

```bash
./run_web.sh
```

Depois acesse:

```text
http://localhost:8000
```

Na interface web voce pode:

- subir a planilha de inscricoes;
- escolher um regulamento pronto do sistema;
- ou enviar um regulamento JSON personalizado;
- ou enviar um regulamento documental em PDF/TXT/MD para analise preliminar;
- processar o ranking ou a analise;
- baixar o Excel final ao termino.

### Modo de analise de regulamento

Quando o usuario envia um regulamento documental em vez de um JSON executavel, a web app gera um Excel de analise com:

- `resumo_analise`
- `colunas_planilha`
- `criterios_detectados`
- `mapeamento_sugerido`
- `regulamento_extraido`
- `config_sugerida`

Esse modo ajuda a equipe a subir um edital e uma planilha de referencia para montar mais rapido a configuracao da nova acao.

## Hospedagem no Azure da ApexBrasil

O projeto agora esta preparado para hospedar em Azure App Service com persistencia dos arquivos em Azure Blob Storage.

### Arquitetura recomendada

- `Azure App Service (Linux, Python)` para hospedar a interface web Flask.
- `Azure Blob Storage` para armazenar planilhas enviadas, regulamentos customizados e Excels gerados.
- `Managed Identity` do App Service para acessar o Blob Storage sem chave no codigo.

### Variaveis de ambiente recomendadas no App Service

```text
JOB_STORAGE_BACKEND=azure_blob
AZURE_STORAGE_ACCOUNT_URL=https://<sua-storage-account>.blob.core.windows.net
AZURE_STORAGE_CONTAINER=ranqueamento-jobs
AZURE_STORAGE_BLOB_PREFIX=jobs
RANQUEAMENTO_SECRET_KEY=<segredo-forte>
```

Opcionalmente, em vez de `AZURE_STORAGE_ACCOUNT_URL`, voce pode usar:

```text
AZURE_STORAGE_CONNECTION_STRING=<connection-string>
```

### Publicacao sugerida no Azure App Service

Com o arquivo [app.py](/Volumes/MMM2tb/Ranqueamento%20de%20Empresas/app.py#L1) na raiz, o Azure App Service consegue detectar o app Flask automaticamente.

Fluxo sugerido:

1. Criar um `App Service` Linux com Python.
2. Criar uma `Storage Account` com um container Blob para os jobs.
3. Habilitar `Managed Identity` no App Service.
4. Conceder ao App Service a role `Storage Blob Data Contributor` na Storage Account ou no container.
5. Configurar as variaveis de ambiente acima.
6. Publicar o codigo via `az webapp up`, GitHub Actions, Azure DevOps ou ZIP deploy.

### Script de deploy para Azure

O projeto agora inclui um script parametrizado em [scripts/deploy_azure_app_service.sh](/Volumes/MMM2tb/Ranqueamento%20de%20Empresas/scripts/deploy_azure_app_service.sh#L1) para:

- criar ou atualizar Resource Group;
- criar Storage Account e container Blob;
- criar App Service Plan e Web App Linux;
- habilitar Managed Identity no App Service;
- conceder `Storage Blob Data Contributor`;
- configurar app settings;
- publicar o projeto via ZIP deploy.

Exemplo de uso:

```bash
cd "/Volumes/MMM2tb/Ranqueamento de Empresas"

export AZ_RESOURCE_GROUP="rg-apex-ranqueamento"
export AZ_LOCATION="brazilsouth"
export AZ_APP_NAME="apex-ranqueamento-web"
export AZ_PLAN_NAME="plan-apex-ranqueamento"
export AZ_STORAGE_ACCOUNT="apexranqueamentostg"
export AZ_STORAGE_CONTAINER="ranqueamento-jobs"
export RANQUEAMENTO_SECRET_KEY="troque-por-um-segredo-forte"

./scripts/deploy_azure_app_service.sh
```

### Observacoes operacionais

- Em desenvolvimento local, o sistema continua usando storage local por padrao.
- Em Azure, o recomendado e `JOB_STORAGE_BACKEND=azure_blob`.
- O upload e o processamento continuam sincronos nesta versao. Para alto volume, o proximo passo seria mover o processamento para fila e worker.

## Rodando com a planilha atual da Jornada Exportadora

Para processar a planilha `Ranqueamento.xlsx` no layout atual:

```bash
./run.sh \
  --entrada "/Users/marcellomartins/Desktop/26.02.09 - Ranqueamento.xlsx" \
  --regulamento config/regulamento_jornada_exportadora_autopartes_2026.json \
  --saida ./saida/jornada_exportadora_autopartes_2026.xlsx
```

Essa configuracao:

- le a aba `Ranqueamento` ou cai automaticamente para a aba ativa da exportacao crua do Dynamics;
- aplica o mapeamento das colunas atuais para campos canonicos;
- executa verificacoes automaticas de CNPJ, website/rede social, idioma estrangeiro e cartao CNPJ;
- reaproveita pontuacoes ja revisadas da planilha quando elas existirem;
- gera sugestoes com revisao humana para criterios que dependem de validacao documental ou confirmacao interna;
- deixa a analise de demanda do mercado-alvo como pendencia de revisao quando esse dado nao estiver na entrada.

Se voce quiser habilitar apoio por IA, exporte a chave antes de rodar:

```bash
export OPENAI_API_KEY="<sua-chave>"
```

## Como rodar os testes

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.vendor python3 -m unittest discover -s tests -v
```
