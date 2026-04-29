
# Obsidian 笔记同步到 GitHub 记录

## 目标

把本地 Obsidian 笔记库：

```text
F:\黑曜石仓库
```

同步到 GitHub 仓库：

```text
https://github.com/mcd6666/Notebook.git
```

---

## 一、初始化 Git 仓库

一开始 `F:\黑曜石仓库` 还不是 Git 仓库，所以先初始化：

```powershell
git init
git branch -M main
git remote add origin https://github.com/mcd6666/Notebook.git
```

后来发现远端仓库已经有一个 `README.md` 初始提交，所以先拉取并合并远端内容：

```powershell
git fetch origin main
git merge origin/main --allow-unrelated-histories --no-edit
```

---

## 二、添加 `.gitignore`

为了避免同步 Obsidian 的临时工作区状态和缓存，添加了 `.gitignore`：

```gitignore
**/.obsidian/workspace.json
**/.obsidian/workspace-mobile.json
**/.obsidian/cache/
**/.trash/
.DS_Store
Thumbs.db
```

这样会同步笔记、图片和必要配置，但不会同步临时界面状态。

---

## 三、首次提交并推送

提交本地笔记：

```powershell
git add .
git commit -m "Initial notebook sync"
```

首次推送时遇到 HTTPS 连接问题：

```text
fatal: unable to access 'https://github.com/mcd6666/Notebook.git/':
Failed to connect to github.com port 443
```

检测后发现：

```text
github.com ping 能通
github.com:443 不通
github.com:22 通
ssh.github.com:443 通
```

说明不是完全没网，而是命令行 Git 直连 GitHub HTTPS 443 端口失败。

---

## 四、改用 SSH 推送

生成了 GitHub 专用 SSH key：

```powershell
ssh-keygen -t ed25519 -C "63773366+mcd6666@users.noreply.github.com" -f C:\Users\DELL\.ssh\id_ed25519_github
```

然后把公钥添加到 GitHub：

```text
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKvM4vfBdHYjYwmW5zd/rZPxQBXeIa2Ajuk9r14pruZ/ 63773366+mcd6666@users.noreply.github.com
```

GitHub 添加位置：

```text
GitHub -> Settings -> SSH and GPG keys -> New SSH key
```

随后把 remote 从 HTTPS 改成 SSH：

```powershell
git remote set-url origin git@github.com:mcd6666/Notebook.git
```

确认 remote：

```powershell
git remote -v
```

结果：

```text
origin  git@github.com:mcd6666/Notebook.git (fetch)
origin  git@github.com:mcd6666/Notebook.git (push)
```

---

## 五、图片无法显示的问题

同步后发现 GitHub 上图片无法显示。

原因是笔记里原来使用的是 Obsidian 专用图片语法：

```md
![[xxx.png]]
```

GitHub 不识别这种语法，所以网页上无法显示。

改成标准 Markdown 图片语法：

```md
![image](../../图片/xxx.png)
```

修改了这些文件中的图片引用：

```text
论文/python学习笔记/深度学习/1.Python学习的两大法宝.md
论文/python学习笔记/深度学习/2.PyTorch加载数据.md
论文/python学习笔记/深度学习/3.Dataset类代码实战.md
```

修复后提交：

```powershell
git add .
git commit -m "Fix image links for GitHub"
```

然后推送：

```powershell
git push
```

推送成功：

```text
To github.com:mcd6666/Notebook.git
   9e56598..a93ef0c  main -> main
```

---

## 六、以后同步笔记的常用命令

以后每次修改笔记后，在：

```powershell
F:\黑曜石仓库
```

执行：

```powershell
git status
git add .
git commit -m "Update notes"
git push
```

如果想先拉取 GitHub 上的更新：

```powershell
git pull
```

---

## 七、下一次新增笔记怎么同步

比如在 Obsidian 里新增了一个文件：

```text
论文/笔记同步github.md
```

先查看当前变化：

```powershell
git status
```

如果看到类似：

```text
new file:   论文/笔记同步github.md
```

说明 Git 已经发现了这个新文件。

然后执行：

```powershell
git add .
git commit -m "Add notebook sync note"
git push
```

其中：

- `git add .`：把新增和修改的文件加入本次提交
- `git commit -m "..."`：保存一个本地版本
- `git push`：同步到 GitHub

提交说明可以自己改，比如：

```powershell
git commit -m "Update notes"
git commit -m "Add deep learning notes"
git commit -m "Fix image links"
```

---

## 八、如果误进 Vim 提交界面

如果执行了：

```powershell
git commit
```

但没有加 `-m "提交说明"`，Git 可能会进入 Vim，界面类似：

```text
# Please enter the commit message for your changes.
# Lines starting with '#' will be ignored.
```

这时有两种处理方式。

### 方法 1：正常完成提交

按键盘：

```text
i
```

进入输入模式，然后在最上面输入提交说明，例如：

```text
Add notebook sync note
```

再按：

```text
Esc
```

输入：

```text
:wq
```

最后按回车，提交就会完成。

### 方法 2：放弃这次提交

如果不想提交，按：

```text
Esc
```

输入：

```text
:q!
```

然后按回车即可退出，不会创建提交。

以后为了避免进入 Vim，推荐始终使用：

```powershell
git commit -m "Update notes"
```

---

## 九、图片同步注意事项

如果笔记中有图片，GitHub 更推荐使用标准 Markdown 图片格式：

```md
![image](../../图片/图片名.png)
```

Obsidian 默认格式是：

```md
![[图片名.png]]
```

这种格式在 Obsidian 里能显示，但 GitHub 网页通常不会显示。

如果只在 Obsidian 本地看，`![[图片名.png]]` 可以继续用；如果希望 GitHub 网页也能显示，就改成标准 Markdown 格式。

---

## 十、创建新的笔记文件夹并同步到另一个仓库

如果要把另一个文件夹单独同步到另一个 GitHub 仓库，例如：

```text
F:\日常随记
```

它应该作为一个独立 Git 仓库来管理，不要和 `F:\黑曜石仓库` 混在一起。

进入新文件夹：

```powershell
cd F:\日常随记
```

如果还不是 Git 仓库，先初始化：

```powershell
git init
git branch -M main
```

添加 `.gitignore`：

```powershell
notepad .gitignore
```

内容仍然可以使用：

```gitignore
**/.obsidian/workspace.json
**/.obsidian/workspace-mobile.json
**/.obsidian/cache/
**/.trash/
.DS_Store
Thumbs.db
```

然后绑定新的 GitHub 仓库。比如新仓库叫 `RS_notebook`：

```powershell
git remote add origin git@github.com:mcd6666/RS_notebook.git
```

如果之前不小心绑定成 HTTPS，例如：

```text
https://github.com/mcd6666/RS_notebook.git
```

可以改成 SSH：

```powershell
git remote set-url origin git@github.com:mcd6666/RS_notebook.git
```

检查当前仓库绑定到了哪里：

```powershell
git remote -v
```

如果显示：

```text
origin  git@github.com:mcd6666/RS_notebook.git (fetch)
origin  git@github.com:mcd6666/RS_notebook.git (push)
```

说明这个文件夹会同步到 `RS_notebook` 仓库。

---

## 十一、新仓库第一次提交和推送

新仓库第一次同步一般执行：

```powershell
git add .
git commit -m "Initial sync"
git push -u origin main
```

第一次推送要加：

```powershell
-u origin main
```

这样 Git 会把本地 `main` 分支和远程 `origin/main` 分支绑定起来。以后就可以直接：

```powershell
git push
```

如果忘了加 `-u`，可能会看到：

```text
fatal: The current branch main has no upstream branch.
```

解决办法：

```powershell
git push -u origin main
```

或者：

```powershell
git push --set-upstream origin main
```

---

## 十二、SSH key 是否需要重新生成

不需要每个仓库都生成一个新的 SSH key。

之前已经生成过这个 GitHub 专用 SSH key：

```text
C:\Users\DELL\.ssh\id_ed25519_github
```

只要是同一台电脑、同一个 GitHub 账号 `mcd6666`，多个仓库都可以共用这个 SSH key。

也就是说，这些仓库都可以使用同一个 key：

```text
F:\黑曜石仓库
F:\日常随记
E:\tide_model
```

前提是 remote 使用 SSH 格式：

```text
git@github.com:mcd6666/仓库名.git
```

不要重复运行：

```powershell
ssh-keygen -t ed25519 -C "63773366+mcd6666@users.noreply.github.com" -f C:\Users\DELL\.ssh\id_ed25519_github
```

除非原来的 key 丢失了，或者想专门换一个新 key。

---

## 十三、HTTPS 连接失败时怎么办

如果看到：

```text
fatal: unable to access 'https://github.com/mcd6666/RS_notebook.git/':
Recv failure: Connection was reset
```

或者：

```text
Failed to connect to github.com port 443
```

说明当前仓库使用 HTTPS remote，而这台电脑的命令行访问 GitHub HTTPS 不稳定。

检查 remote：

```powershell
git remote -v
```

如果看到：

```text
origin  https://github.com/mcd6666/RS_notebook.git (fetch)
origin  https://github.com/mcd6666/RS_notebook.git (push)
```

改成 SSH：

```powershell
git remote set-url origin git@github.com:mcd6666/RS_notebook.git
```

然后再推送：

```powershell
git push
```

如果是第一次推送：

```powershell
git push -u origin main
```

---

## 十四、空文件夹为什么没有上传

Git 可以跟踪空文件，但不会跟踪空文件夹。

如果一个文件夹是空的，GitHub 上不会显示它。这是 Git 的正常机制。

解决办法是在空文件夹里放一个占位文件，常用名字是：

```text
.gitkeep
```

例如要保留这个空文件夹：

```text
F:\日常随记\图片
```

可以执行：

```powershell
New-Item -ItemType File -Path "F:\日常随记\图片\.gitkeep"
```

然后提交：

```powershell
cd F:\日常随记
git add .
git commit -m "Add empty folders"
git push
```

如果是空的 `.md` 文件，Git 是可以上传的。只要执行：

```powershell
git add .
git commit -m "Add empty note"
git push
```

---

## 十五、如何查看 SSH 公钥

如果 GitHub 要添加 SSH key，可以查看公钥文件：

```powershell
type C:\Users\DELL\.ssh\id_ed25519_github.pub
```

输出会是一整行，类似：

```text
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA... 63773366+mcd6666@users.noreply.github.com
```

把整行复制到 GitHub：

```text
GitHub -> Settings -> SSH and GPG keys -> New SSH key
```

也可以直接复制到剪贴板：

```powershell
type C:\Users\DELL\.ssh\id_ed25519_github.pub | clip
```

---

## 十六、当前结果

- 本地 Obsidian 笔记库已经变成 Git 仓库
- 已连接 GitHub 仓库 `mcd6666/Notebook`
- 已改用 SSH，绕开 HTTPS 443 连接问题
- 图片链接已改成 GitHub 可显示的 Markdown 格式
- 最新提交已成功推送到 GitHub

当前 GitHub 仓库：

```text
git@github.com:mcd6666/Notebook.git
```
