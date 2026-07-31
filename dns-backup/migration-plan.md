# unryu.org のDNSをCloudflareへ移す手順

作成日 2026年7月31日。

ドメインの登録先はValue Domainのまま変えない。変えるのはネームサーバだけである。
Value Domainのネームサーバに紐づく機能（メール転送、URL転送）はCloudflare側の機能で置き換える。

## なぜ移すのか

- `https://www.unryu.org` の証明書がGitHub側で発行されず、20時間以上動いていない。
  既存のapex専用証明書が有効なため、GitHubが新しい証明書を要求していないとみられる。
  自然発行を待つと有効期限の更新期、つまり9月下旬になる。
- Value DomainのURL転送はhttpsに対応しておらず、`lab.unryu.org` が現在まったく使えない。
- Cloudflareに移すと、証明書の自動発行とhttps対応のリダイレクトが同時に手に入る。

---

## 移行前のDNSレコード（復旧用の控え）

`dns-snapshot.txt` に権威サーバへ直接問い合わせた生の結果がある。以下はその整理である。

| 名前 | 種別 | 値 | 用途 | 移行後の扱い |
| --- | --- | --- | --- | --- |
| `@` | NS | `01〜04.dnsv.jp` | Value DomainのDNS | Cloudflareのものに変更 |
| `@` | A | `185.199.108.153` | GitHub Pages | そのまま作る |
| `@` | A | `185.199.109.153` | GitHub Pages | そのまま作る |
| `@` | A | `185.199.110.153` | GitHub Pages | そのまま作る |
| `@` | A | `185.199.111.153` | GitHub Pages | そのまま作る |
| `@` | MX | `10 mailforward.dnsv.jp` | メール転送 | **Email Routingが自動で置き換える** |
| `www` | CNAME | `qurihara.github.io` | サイト本体 | そのまま作る |
| `bc` | A | `133.99.41.113` | 別サーバ | そのまま作る |
| `core` | A | `133.99.41.112` | 別サーバ | そのまま作る |
| `dev` | A | `133.99.41.114` | 別サーバ | そのまま作る |
| `lab` | A | `157.7.174.95` | URL転送の受け先 | **不要。リダイレクトで置き換え** |
| `sj` | A | `157.7.174.95` | URL転送の受け先 | **不要。リダイレクトで置き換え** |
| `pjwdrjv7hee5` | CNAME | `gv-gq435w5kutliwe.dv.googlehosted.com` | Googleの所有権確認 | そのまま作る |
| `q5rhpoeepiqs` | CNAME | `gv-7gmr7lfb7lbaea.dv.googlehosted.com` | Googleの所有権確認 | そのまま作る |

TTLはいずれも300秒。AAAA、TXT、CAAは未設定である。

### Value DomainのURL転送（DNSレコードではないが控えておく）

| 名前 | 転送先 |
| --- | --- |
| `lab` | `https://www.unryu.org/home/lab` |
| `sj` | `https://sites.google.com/site/qurihara/top-english/speechjammer` |

`lab` の転送先 `/home/lab` は現在のサイトに存在しないパスである。移行を機に
`https://unryu.org/lab` へ直すのがよい。

---

## Cloudflareでの設定内容

### プロキシの扱い

Cloudflareのプロキシ（オレンジ色の雲）を有効にすると、DNSが返すIPがCloudflareのものになる。
そのためGitHub Pagesは証明書を取得・更新できなくなる。これはGitHubのスタッフも認めている。

**それでよい。** 証明書はCloudflareが用意し、apexとwwwの両方を自動で覆う。
GitHubの証明書に依存しなくなることが、今回の移行の目的そのものである。

| 名前 | 種別 | 値 | プロキシ |
| --- | --- | --- | --- |
| `@` | A | `185.199.108.153` | 有効 |
| `@` | A | `185.199.109.153` | 有効 |
| `@` | A | `185.199.110.153` | 有効 |
| `@` | A | `185.199.111.153` | 有効 |
| `www` | CNAME | `qurihara.github.io` | 有効 |
| `bc` | A | `133.99.41.113` | 無効（DNSのみ） |
| `core` | A | `133.99.41.112` | 無効（DNSのみ） |
| `dev` | A | `133.99.41.114` | 無効（DNSのみ） |
| `pjwdrjv7hee5` | CNAME | `gv-gq435w5kutliwe.dv.googlehosted.com` | 無効（DNSのみ） |
| `q5rhpoeepiqs` | CNAME | `gv-7gmr7lfb7lbaea.dv.googlehosted.com` | 無効（DNSのみ） |

`bc` `core` `dev` は別のサーバで動いており、証明書の状況が分からない。
プロキシを通すと不具合が出る恐れがあるため、DNSのみとして現状の挙動を保つ。

Googleの所有権確認用CNAMEは、プロキシを通すと確認に失敗する。必ずDNSのみにする。

### SSL/TLSの設定

**「Full」を選ぶ。** 理由は次のとおり。

- `Flexible` はCloudflareからGitHubへ暗号化なしで送るため、GitHub側でHTTPS強制が有効だと
  リダイレクトの無限ループ（ERR_TOO_MANY_REDIRECTS）が起きる。
- `Full (Strict)` はオリジンの証明書のホスト名一致を要求する。
  現在 `www.unryu.org` には `*.github.io` の証明書が返るため一致せず、Error 526 になる。
- `Full` は暗号化しつつ証明書の検証をしないため、この構成で成立する。

### リダイレクト（URL転送の置き換え）

Cloudflareのリダイレクトルールで作る。**httpsに対応する**ことが、Value Domainとの違いである。

| 元 | 先 |
| --- | --- |
| `lab.unryu.org/*` | `https://unryu.org/lab` |
| `sj.unryu.org/*` | `https://sites.google.com/site/qurihara/top-english/speechjammer` |

### メール転送（Email Routing）

Cloudflare Email Routing を使う。無料である。

- 宛先としてGmailのアドレスを登録し、届く確認メールで承認する
- キャッチオールを有効にすると、`unryu.org` 宛のどのアドレスでも受け取れる
- MX と SPF のレコードはCloudflareが自動で作る
- 送信（Send As）はできないが、今回の要件は受信の転送だけなので問題ない
- 上限は、転送ルールが1ドメイン200件、宛先アドレスがアカウント全体で200件、
  受信メールの大きさが25MiBまで

---

## 作業の順番

メールが宙に浮く時間を最短にするため、**転送の準備を先に済ませてからネームサーバを切り替える。**

1. Cloudflareのアカウントを作り、`unryu.org` を追加する（栗原さん）
2. 取り込まれたDNSレコードを上の表と照合する（私）
3. Email Routing で宛先のGmailを登録し、確認メールを承認する（栗原さん）
4. キャッチオールを有効にする（私が手順を示し、栗原さんが操作）
5. SSL/TLSモードを Full にする（私が手順を示す）
6. リダイレクトルールを2件作る（同上）
7. **Value Domainでネームサーバを変更する**（栗原さん）。ここが切り替えの瞬間である
8. 反映後、メールの到達、サイトの表示、証明書、プロジェクトサイト35件を検証する（私）
9. GitHub側のカスタムドメイン設定をどうするか判断する（証明書はCloudflareが持つため）

---

## 元に戻す方法

不都合があれば、Value Domainでネームサーバを `01.dnsv.jp` から `04.dnsv.jp` に戻す。
そのうえで、この文書の「移行前のDNSレコード」の表どおりにレコードを入力し直す。
メール転送とURL転送もValue Domain側で設定し直す。

ネームサーバの変更が行き渡るまでに時間がかかる点は、行きも戻りも同じである。

---

## 移行の結果（2026年7月31日 11時20分）

**すべて成功した。** GitHub Pagesで3日近く発行されなかった証明書が、Cloudflareへの移行で即座に解決した。

### 発行された証明書

```
発行者: Google Trust Services（Cloudflare経由）
対象  : DNS:unryu.org, DNS:*.unryu.org
発行  : 2026年7月31日
```

すべてのサブドメインを覆うため、今後サブドメインを増やしても証明書の心配がない。

### 検証した結果

| 対象 | 結果 |
| --- | --- |
| 全57ページ（www経由） | 57件すべて正常 |
| `https://www.unryu.org` | 200。`https://unryu.org/` へ転送 |
| `https://unryu.org` | 200 |
| `http://www.unryu.org` | 200 |
| 下層ページ | profile、publications、lab、home/kotodama すべて200 |
| プロジェクトサイト | ai-fue、chordika、ez_karuta、IgNobelPrize2012、iFont、breath-detector すべて200 |
| メール転送 | MX 3件とSPFを実測で確認。Email Routingは「有効」 |

### 途中で分かった、想定と違った点

- **Cloudflareはゾーンがアクティブになるまでメール用DNSレコードを追加できない。**
  準備を完全に終えてから切り替えるという段取りは取れず、切り替え後に追加した。
- **旧MXレコードが残っていると追加できない。**
  「既存の非Cloudflare MXレコードが競合しています」と出るため、`mailforward.dnsv.jp` を削除してから追加した。
- **Value Domainには似た画面が2つある。**
  `moddns.php` はDNSレコードの編集画面で、ここのNS行を書き換えても委任は変わらない。
  正しくは左メニューの「ネームサーバーの設定」（`modns.php`）である。
- **自動取り込みで4件が漏れた。**
  `bc`、`core`、Googleの所有権確認用CNAME 2件。控えを取っておいたことで気づけた。

### lab と sj

Value DomainのURL転送用だったAレコードは引き継いでいない。現在は名前解決されない。
ほぼ使っていないという判断により、このまま放置とした。
必要になればCloudflareのリダイレクトルールで設定でき、その場合はhttpsにも対応する。
