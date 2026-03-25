#!/bin/zsh
set -euo pipefail

cd "$(dirname "$0")/.."

: "${AZ_RESOURCE_GROUP:?Defina AZ_RESOURCE_GROUP}"
: "${AZ_LOCATION:?Defina AZ_LOCATION, por exemplo brazilsouth}"
: "${AZ_APP_NAME:?Defina AZ_APP_NAME}"
: "${AZ_PLAN_NAME:?Defina AZ_PLAN_NAME}"
: "${AZ_STORAGE_ACCOUNT:?Defina AZ_STORAGE_ACCOUNT}"
: "${AZ_STORAGE_CONTAINER:=ranqueamento-jobs}"
: "${AZ_SKU:=B1}"
: "${AZ_RUNTIME:=PYTHON|3.12}"
: "${RANQUEAMENTO_SECRET_KEY:?Defina RANQUEAMENTO_SECRET_KEY}"

if ! command -v az >/dev/null 2>&1; then
  echo "Azure CLI (az) nao encontrado no PATH." >&2
  exit 1
fi

if ! command -v zip >/dev/null 2>&1; then
  echo "Comando zip nao encontrado no PATH." >&2
  exit 1
fi

echo "Criando ou atualizando Resource Group..."
az group create \
  --name "$AZ_RESOURCE_GROUP" \
  --location "$AZ_LOCATION" \
  >/dev/null

echo "Criando ou atualizando Storage Account..."
az storage account create \
  --name "$AZ_STORAGE_ACCOUNT" \
  --resource-group "$AZ_RESOURCE_GROUP" \
  --location "$AZ_LOCATION" \
  --sku Standard_LRS \
  --allow-blob-public-access false \
  >/dev/null

echo "Criando container Blob..."
az storage container create \
  --name "$AZ_STORAGE_CONTAINER" \
  --account-name "$AZ_STORAGE_ACCOUNT" \
  --auth-mode login \
  >/dev/null

echo "Criando ou atualizando App Service Plan..."
az appservice plan create \
  --name "$AZ_PLAN_NAME" \
  --resource-group "$AZ_RESOURCE_GROUP" \
  --is-linux \
  --sku "$AZ_SKU" \
  >/dev/null

echo "Criando ou atualizando Web App..."
if ! az webapp show --resource-group "$AZ_RESOURCE_GROUP" --name "$AZ_APP_NAME" >/dev/null 2>&1; then
  az webapp create \
    --resource-group "$AZ_RESOURCE_GROUP" \
    --plan "$AZ_PLAN_NAME" \
    --name "$AZ_APP_NAME" \
    --runtime "$AZ_RUNTIME" \
    >/dev/null
fi

echo "Habilitando Managed Identity..."
PRINCIPAL_ID="$(
  az webapp identity assign \
    --resource-group "$AZ_RESOURCE_GROUP" \
    --name "$AZ_APP_NAME" \
    --query principalId \
    --output tsv
)"

STORAGE_SCOPE="$(
  az storage account show \
    --resource-group "$AZ_RESOURCE_GROUP" \
    --name "$AZ_STORAGE_ACCOUNT" \
    --query id \
    --output tsv
)"

echo "Garantindo permissao Storage Blob Data Contributor..."
az role assignment create \
  --assignee-object-id "$PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Storage Blob Data Contributor" \
  --scope "$STORAGE_SCOPE" \
  >/dev/null 2>&1 || true

echo "Configurando variaveis de ambiente..."
az webapp config appsettings set \
  --resource-group "$AZ_RESOURCE_GROUP" \
  --name "$AZ_APP_NAME" \
  --settings \
    SCM_DO_BUILD_DURING_DEPLOYMENT=true \
    JOB_STORAGE_BACKEND=azure_blob \
    AZURE_STORAGE_ACCOUNT_URL="https://${AZ_STORAGE_ACCOUNT}.blob.core.windows.net" \
    AZURE_STORAGE_CONTAINER="$AZ_STORAGE_CONTAINER" \
    AZURE_STORAGE_BLOB_PREFIX=jobs \
    RANQUEAMENTO_SECRET_KEY="$RANQUEAMENTO_SECRET_KEY" \
  >/dev/null

echo "Montando pacote ZIP de deploy..."
TMP_ZIP="$(mktemp -t ranqueamento-azure-deploy).zip"
rm -f "$TMP_ZIP"

zip -r "$TMP_ZIP" . \
  -x ".git/*" \
     ".venv/*" \
     ".vendor/*" \
     "storage/*" \
     "saida/*" \
     "__pycache__/*" \
     "*.pyc" \
     "._*" \
     ".DS_Store" \
  >/dev/null

echo "Enviando aplicacao para Azure App Service..."
az webapp deploy \
  --resource-group "$AZ_RESOURCE_GROUP" \
  --name "$AZ_APP_NAME" \
  --src-path "$TMP_ZIP" \
  --type zip \
  >/dev/null

rm -f "$TMP_ZIP"

DEFAULT_HOSTNAME="$(
  az webapp show \
    --resource-group "$AZ_RESOURCE_GROUP" \
    --name "$AZ_APP_NAME" \
    --query defaultHostName \
    --output tsv
)"

echo "Deploy concluido."
echo "URL: https://${DEFAULT_HOSTNAME}"
