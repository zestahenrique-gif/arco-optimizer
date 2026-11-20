# Arco Optimizer: como gerar o .exe e o .app sem instalar nada

O GitHub compila os dois para voce, de graca, nos servidores dele.

1. Crie uma conta em github.com (se ainda nao tiver).
2. Clique em "New repository", de o nome arco-optimizer e crie.
3. Envie estes arquivos: "Add file" > "Upload files" e arraste ArcoOptimizer.py e a pasta .github
   (se a pasta .github nao subir, use "Add file" > "Create new file", digite
   .github/workflows/build.yml e cole o conteudo do arquivo build.yml).
4. Abra a aba "Actions" > "Gerar Arco Optimizer" > "Run workflow".
5. Espere uns 3 minutos. Abra a execucao concluida e baixe, em "Artifacts":
   - ArcoOptimizer-Windows  (ArcoOptimizer.exe)
   - ArcoOptimizer-macOS    (Arco Optimizer.app dentro de um zip)

Para ter links de download publicos para o site: crie uma tag (ex.: v1.0.0) em "Releases".
Os arquivos aparecem na pagina da release e voce cola esses links no site.

Aviso: os apps nao sao assinados. O Windows mostra "Mais informacoes > Executar assim mesmo"
e no Mac o primeiro uso e com botao direito > Abrir.
