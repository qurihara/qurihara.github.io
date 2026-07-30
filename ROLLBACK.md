# 緊急時に Google Sites 運用へ戻す手順

このサイトは Google Sites から GitHub Pages へ移した。
何か問題が起きたときに Google Sites の運用へ戻せるよう、戻し方をここに残す。

**最初に読むこと。** 元の Google Sites は削除していない。編集画面もそのまま残っている。
したがって戻す作業は「DNSの向き先を戻すだけ」で足り、コンテンツの復元は要らない。
所要時間は入力そのものは数分で、反映を待つ時間が加わる。

---

## 1. まず切り分ける

あわてて戻す前に、何が壊れているのかを見る。GitHub Pages 側だけの問題なら、
DNSを戻すより先に前の状態へ戻すほうが速い場合がある。

```bash
# サイトが応答するか
curl -sI https://unryu.org/ | head -3

# 配信しているのがどちらか。GitHub なら server: GitHub.com、Google なら server: ESF
curl -sI https://unryu.org/ | grep -i '^server:'
curl -sI https://www.unryu.org/ | grep -i '^server:'

# DNSの現在の向き先
dig +short @01.dnsv.jp unryu.org A
dig +short @01.dnsv.jp www.unryu.org CNAME

# GitHub Pages 側の状態（ドメイン、証明書）
gh api repos/qurihara/qurihara.github.io/pages \
  --jq '{cname, cert: .https_certificate.state, https_enforced, status}'
```

判断の目安は次のとおり。

| 症状 | 戻す範囲 |
| --- | --- |
| 見た目が崩れた、内容を壊した | DNSは触らない。第4節「サイトの中身だけ戻す」 |
| 証明書のエラーが出る | DNSは触らない。第5節「証明書だけの問題」 |
| サイト全体が見られない、GitHubの障害 | 第2節「DNSを Google Sites へ戻す」 |

---

## 2. DNSを Google Sites へ戻す（全面的に戻す）

Value Domain の管理画面で unryu.org のDNSレコードを編集する。
ネームサーバは 01〜04.dnsv.jp で、Value Domain のDNSを使っている。

### 2-1. www を Google Sites へ戻す

`www` の CNAME の値を次に戻す。

| 名前 | 種類 | 戻す値 |
| --- | --- | --- |
| `www` | CNAME | `ghs.googlehosted.com.` |

移行後は `qurihara.github.io.` になっているので、これを上の値に書き換える。

### 2-2. 裸のドメインをどうするか

移行前、裸の `unryu.org` は次の値だった。

| 名前 | 種類 | 移行前の値 |
| --- | --- | --- |
| `@` | A | `157.7.174.95` |

ただし**この設定は元から機能しておらず、404を返していた**。
逆引きすると `unused-157-7-174-095.interq.or.jp` で、GMOの未使用のIPだった。
つまり移行前は「www付きでしかアクセスできない」状態だった。

したがって選べる道は2つある。

- **完全に移行前と同じにする。** `@` の4つのAレコード（185.199.108〜111.153）を削除し、
  `@ A 157.7.174.95` を1行だけ戻す。裸のドメインは再び404になる。
- **裸のドメインを生かしたまま Google Sites に戻す。**
  `@` のAレコードは消さずに残す。この場合、裸のドメインは GitHub Pages を、
  www は Google Sites を指す状態になる。両方が別々に見える。
  一時しのぎとしては使えるが、同じ内容が2か所にある状態なので長く置かない。

**迷ったら前者を選ぶ。** 移行前とまったく同じ状態に戻る。

### 2-3. 触ってはいけないレコード

次のものは移行で変更していない。戻す作業でも触らない。

| 名前 | 種類 | 値 | 用途 |
| --- | --- | --- | --- |
| `@` | NS | `01〜04.dnsv.jp` | Value Domain のDNS |
| `@` | MX | `mailforward.dnsv.jp`（優先度10） | **メール転送。消すとメールが届かなくなる** |
| `bc` | A | `133.99.41.113` | 別サーバ |
| `core` | A | `133.99.41.112` | 別サーバ |
| `dev` | A | `133.99.41.114` | 別サーバ |
| `lab` | A | `157.7.174.95` | URL転送の受け先 |
| `sj` | A | `157.7.174.95` | URL転送の受け先 |
| `lab` | URL転送 | `https://www.unryu.org/...` | 転送設定 |
| `sj` | URL転送 | `https://sites.google.c...` | 転送設定 |
| `pjwdrjv7hee5` | CNAME | `gv-gq435w5kutliwe...` | Googleの所有権確認 |
| `q5rhpoeepiqs` | CNAME | `gv-7gmr7lfb7lbaea...` | Googleの所有権確認 |

Googleの所有権確認用のCNAME 2件は、移行後も残してある。
これがあるおかげで、Google Sites 側でドメインの再設定がすぐにできる。**消さないこと。**

### 2-4. GitHub Pages 側の独自ドメイン設定を外す

DNSを戻したら、GitHub 側からも独自ドメインの指定を外す。
外さないと GitHub が unryu.org を自分のものとして扱い続ける。

```bash
gh api -X PUT repos/qurihara/qurihara.github.io/pages -f cname=''
```

あわせて、リポジトリから CNAME ファイルを消す。

```bash
cd unryu-site-clone
git rm docs/CNAME
git commit -m "独自ドメインの指定を外した"
git push origin main
```

CNAME ファイルを残したままだと、次のビルドで独自ドメインが再設定されることがある。

### 2-5. 反映を待って確認する

TTLは300秒（5分）と短いので、反映は速い。

```bash
# Google に戻っていれば server: ESF が返る
curl -sI https://www.unryu.org/ | grep -i '^server:'
```

証明書は Google 側が持っているため、www は元から https で見られる。

---

## 3. Google Sites 側でドメインを再設定する場合

上の手順で戻らない場合、Google Sites 側のカスタムドメイン設定が外れている可能性がある。
Google Sites の編集画面を開き、設定メニューの「カスタムドメイン」で `www.unryu.org` を
関連付け直す。所有権の確認を求められたら Google Search Console で行う。
DNSに置いたままの `pjwdrjv7hee5` と `q5rhpoeepiqs` のCNAMEが、この確認に使われる。

反映には最長48時間かかると案内されるが、DNSが正しければ通常はもっと早い。

---

## 4. サイトの中身だけ戻す（DNSは触らない）

見た目を壊した、内容を消してしまった、という場合はDNSと無関係である。
GitHub Pages のまま、前の状態へ戻せばよい。

### 見た目だけ戻す

```bash
cd unryu-site-clone
git checkout baseline-v1 -- assets/style.css
python3 tools/render_site.py
git commit -am "見た目をベースライン版に戻した"
git push origin main
```

### サイト全体を、表示を整え終えた時点へ戻す

`baseline-v1` は、内容の取り込みと表示の調整を終えた時点の目印である。

```bash
cd unryu-site-clone
git reset --hard baseline-v1
git push --force origin main
```

`--force` は履歴を書き換える。実行前に、戻したい時点が本当に `baseline-v1` かを確かめる。

```bash
git log --oneline baseline-v1 -1
git tag -n99 baseline-v1
```

### ひとつ前のコミットに戻す

```bash
cd unryu-site-clone
git revert HEAD
git push origin main
```

`revert` は履歴を消さずに打ち消すコミットを足すため、`reset --hard` より安全である。

---

## 5. 証明書だけの問題

`https://unryu.org` で証明書のエラーが出る場合、多くはDNSを変えた直後に
GitHub がまだ証明書を発行できていない状態である。DNSを戻す必要はない。

```bash
# 発行状況を見る。approved なら発行済み
gh api repos/qurihara/qurihara.github.io/pages --jq '.https_certificate.state'

# 実際にどの証明書が返っているか。CN=unryu.org になっていれば正しい
echo | openssl s_client -connect unryu.org:443 -servername unryu.org 2>/dev/null \
  | openssl x509 -noout -subject -dates
```

`*.github.io` が返る場合は、まだ配信サーバへ行き渡っていない。数分から数十分待つ。

発行が始まらない場合は、いったん独自ドメインを外して入れ直すと再発行が走る。

```bash
gh api -X PUT repos/qurihara/qurihara.github.io/pages -f cname=''
sleep 30
gh api -X PUT repos/qurihara/qurihara.github.io/pages -f cname=unryu.org
```

---

## 6. 記録しておく値の一覧

移行前と移行後の対応をまとめる。戻すときはこの表の「移行前」の列にする。

| 名前 | 種類 | 移行前 | 移行後 |
| --- | --- | --- | --- |
| `@` | A | `157.7.174.95`（404だった） | `185.199.108.153` `185.199.109.153` `185.199.110.153` `185.199.111.153` |
| `www` | CNAME | `ghs.googlehosted.com.` | `qurihara.github.io.` |

GitHub 側の設定。

| 項目 | 値 |
| --- | --- |
| リポジトリ | `qurihara/qurihara.github.io` |
| 公開元 | `main` ブランチの `/docs` フォルダ |
| 独自ドメイン | `unryu.org` |
| HTTPS強制 | 有効 |
| 戻す目印のタグ | `baseline-v1` |
| 旧Hexoの内容 | `hexo-2015-backup` ブランチ |

---

## 7. 覚えておくとよいこと

- **Google Sites は消さない。** 戻す手段として残しておく。
  少なくとも移行後しばらくは、編集画面もそのままにしておく。
- **MXレコードは移行と無関係。** メール転送はDNSのAレコードやCNAMEを変えても影響を受けない。
  逆に言えば、戻す作業でMXを触る理由もない。
- **TTLは300秒。** DNSの変更は5分ほどで行き渡る。長く変わらないときは、
  保存操作が完了していない可能性を先に疑う。権威サーバへ直接問い合わせると切り分けられる。
- **Googleの所有権確認用CNAMEは残してある。** Google Sites へ戻すときの手間が減る。
- 現在のサイトの内容は、この作業フォルダと GitHub リポジトリの両方にある。
  Google Sites が万一消えても、内容そのものは失われない。
