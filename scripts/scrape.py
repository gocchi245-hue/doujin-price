import json
import os
import re
from datetime import datetime
from playwright.sync_api import sync_playwright


def scrape_dlsite_ranking(page):
    """DLsiteの同人ランキングを取得"""
    print("[DLsite] ランキング取得開始")
    items = []

    try:
        page.goto('https://www.dlsite.com/maniax/ranking/day', timeout=60000)
        page.wait_for_timeout(5000)

        links = page.query_selector_all('a[href*="/product_id/RJ"]')
        print(f"[DLsite] product_idリンク数: {len(links)}")

        seen_ids = set()
        rank = 0
        for link in links:
            href = link.get_attribute('href') or ''
            match = re.search(r'product_id/(RJ\d+)', href)
            if not match:
                continue
            pid = match.group(1)
            if pid in seen_ids:
                continue
            seen_ids.add(pid)
            rank += 1
            if rank > 30:
                break

            title = link.get_attribute('title') or link.inner_text().strip()
            if not title or len(title) < 2:
                title = pid

            items.append({
                'rank': rank,
                'title': title,
                'circle': '',
                'genre': 'その他',
                'price': 0,
                'originalPrice': None,
                'tags': [],
                'dlsiteUrl': f"https://www.dlsite.com/maniax/work/=/product_id/{pid}.html",
                'productId': pid,
                'rating': None,
                'emoji': '📄',
                'isOnSale': False,
                'fanzaPrice': None,
                'fanzaUrl': '',
            })

        print(f"[DLsite] ユニーク作品数: {len(items)}")

        # 詳細ページから情報取得
        for item in items[:20]:
            try:
                page.goto(item['dlsiteUrl'], timeout=30000)
                page.wait_for_timeout(2000)

                title_el = page.query_selector('#work_name, [id*="work_name"]')
                if title_el:
                    item['title'] = title_el.inner_text().strip()

                circle_el = page.query_selector('[class*="maker_name"] a')
                if circle_el:
                    item['circle'] = circle_el.inner_text().strip()

                # 価格取得を改善: 複数のセレクターを試す
                price = 0
                for selector in [
                    '.work_buy_content .price',
                    '[class*="work_buy"] [class*="price"]',
                    '.work_price',
                    '#work_price',
                ]:
                    price_el = page.query_selector(selector)
                    if price_el:
                        price_text = price_el.inner_text().strip()
                        # 「円」の前の数値を取得
                        price_match = re.search(r'([\d,]+)\s*円', price_text)
                        if price_match:
                            price = int(price_match.group(1).replace(',', ''))
                            break
                        # カンマ区切りの数値を取得（100以上のもの）
                        nums = re.findall(r'[\d,]+', price_text)
                        for n in nums:
                            val = int(n.replace(',', ''))
                            if val >= 100:
                                price = val
                                break
                    if price > 0:
                        break

                item['price'] = price

                tag_els = page.query_selector_all('[class*="work_genre"] a, [class*="genre"] a')
                item['tags'] = [t.inner_text().strip() for t in tag_els[:5] if t.inner_text().strip()]

                all_text = item['title'] + ' ' + ' '.join(item['tags'])
                for g, kws in {
                    'RPG': ['RPG', 'ロールプレイング'],
                    '音声': ['音声', 'ASMR', 'ボイス', 'バイノーラル'],
                    'CG集': ['CG', 'イラスト集'],
                    'ノベル': ['ノベル', 'ADV', 'アドベンチャー'],
                    'マンガ': ['マンガ', '漫画', 'コミック'],
                    'アクション': ['アクション', 'ACT'],
                    'シミュレーション': ['シミュレーション', 'SLG'],
                    '動画': ['動画', 'アニメーション'],
                }.items():
                    if any(kw in all_text for kw in kws):
                        item['genre'] = g
                        break

                emoji_map = {'RPG':'⚔️','音声':'🎵','CG集':'🎨','ノベル':'📖','マンガ':'📚','アクション':'🎮','シミュレーション':'🏰','動画':'🎬','その他':'📄'}
                item['emoji'] = emoji_map.get(item['genre'], '📄')

                print(f"  [{item['rank']}] {item['title'][:30]} / {item['circle']} / ¥{item['price']}")

            except Exception as e:
                print(f"  [{item['rank']}] 詳細取得失敗: {e}")

    except Exception as e:
        print(f"[DLsite] エラー: {e}")

    print(f"[DLsite] 合計{len(items)}件取得完了")
    return items


def scrape_fanza_ranking(browser):
    """FANZAの同人ランキングをCookie設定でスクレイピング"""
    print("[FANZA] ランキング取得開始")
    fanza_data = {}

    # 年齢認証済みCookieを設定した新しいコンテキスト
    context = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    )

    # 年齢認証Cookieを事前に設定
    context.add_cookies([
        {'name': 'age_check_done', 'value': '1', 'domain': '.dmm.co.jp', 'path': '/'},
        {'name': 'age_check_done', 'value': '1', 'domain': '.dmm.com', 'path': '/'},
        {'name': 'is_intarnal', 'value': '1', 'domain': '.dmm.co.jp', 'path': '/'},
        {'name': 'ckcy', 'value': '1', 'domain': '.dmm.co.jp', 'path': '/'},
        {'name': 'cklg', 'value': 'ja', 'domain': '.dmm.co.jp', 'path': '/'},
    ])

    page = context.new_page()

    try:
        # まずトップページで年齢認証を通す
        page.goto('https://www.dmm.co.jp/top/', timeout=30000)
        page.wait_for_timeout(2000)

        # 年齢認証ボタンが表示されたらクリック
        for selector in [
            'a:has-text("はい")',
            'a:has-text("Yes")',
            '.ageCheck__link--yes',
            'a[href*="age_check"][href*="yes"]',
            'button:has-text("はい")',
        ]:
            btn = page.query_selector(selector)
            if btn:
                print(f"[FANZA] 年齢認証ボタンをクリック: {selector}")
                btn.click()
                page.wait_for_timeout(3000)
                break

        print(f"[FANZA] トップページ通過: {page.title()}")

        # 同人ランキングページにアクセス
        ranking_urls = [
            'https://www.dmm.co.jp/dc/doujin/-/ranking/=/term=daily/',
            'https://www.dmm.co.jp/dc/doujin/-/ranking/',
            'https://www.dmm.co.jp/dc/doujin/',
        ]

        for url in ranking_urls:
            print(f"[FANZA] アクセス試行: {url}")
            page.goto(url, timeout=30000)
            page.wait_for_timeout(3000)

            # 年齢認証が再度表示されたらクリック
            for sel in ['a:has-text("はい")', '.ageCheck__link--yes']:
                btn = page.query_selector(sel)
                if btn:
                    btn.click()
                    page.wait_for_timeout(3000)
                    break

            current_title = page.title()
            current_url = page.url
            print(f"[FANZA] ページタイトル: {current_title}")
            print(f"[FANZA] URL: {current_url}")

            # ログインページでなければ成功
            if 'ログイン' not in current_title and 'login' not in current_url.lower():
                break

        # 作品リンクを取得（様々なパターンで試行）
        work_links = []
        for selector in [
            'a[href*="/dc/doujin/-/detail/"]',
            'a[href*="doujin"][href*="cid="]',
            '.rank-list a[href*="doujin"]',
            '.rankingList a[href*="doujin"]',
            'a[href*="/digital/doujin/"]',
            'p.tmb a[href*="doujin"]',
            'li a[href*="doujin"]',
        ]:
            work_links = page.query_selector_all(selector)
            if work_links:
                print(f"[FANZA] セレクター '{selector}' で {len(work_links)}件発見")
                break

        if not work_links:
            # フォールバック: ページ内の全リンクからdoujin関連を抽出
            all_links = page.query_selector_all('a[href]')
            print(f"[FANZA] 全リンク数: {len(all_links)}")
            for link in all_links:
                href = link.get_attribute('href') or ''
                if 'doujin' in href and ('detail' in href or 'cid=' in href):
                    work_links.append(link)

        print(f"[FANZA] 作品リンク数: {len(work_links)}")

        seen = set()
        for link in work_links:
            href = link.get_attribute('href') or ''
            title = link.get_attribute('title') or ''

            if not title:
                img = link.query_selector('img')
                if img:
                    title = img.get_attribute('alt') or ''

            if not title:
                title = link.inner_text().strip()

            if not title or len(title) < 3 or title in seen:
                continue

            seen.add(title)

            if href.startswith('//'):
                href = 'https:' + href
            elif href.startswith('/'):
                href = 'https://www.dmm.co.jp' + href

            fanza_data[title] = {'url': href, 'price': None}

        print(f"[FANZA] ユニーク作品数: {len(fanza_data)}")

        # 上位作品の詳細ページから価格取得
        count = 0
        for title, data in list(fanza_data.items()):
            if count >= 15:
                break
            if not data['url']:
                continue
            try:
                page.goto(data['url'], timeout=30000)
                page.wait_for_timeout(2000)

                # 年齢認証
                for sel in ['a:has-text("はい")', '.ageCheck__link--yes']:
                    btn = page.query_selector(sel)
                    if btn:
                        btn.click()
                        page.wait_for_timeout(2000)
                        break

                # 価格取得
                for selector in [
                    '.price',
                    '[class*="price"]',
                    '[class*="Price"]',
                    'span:has-text("円")',
                ]:
                    price_el = page.query_selector(selector)
                    if price_el:
                        price_text = price_el.inner_text().strip()
                        price_match = re.search(r'([\d,]+)\s*円', price_text)
                        if price_match:
                            data['price'] = int(price_match.group(1).replace(',', ''))
                            break
                        nums = re.findall(r'[\d,]+', price_text)
                        for n in nums:
                            val = int(n.replace(',', ''))
                            if val >= 100:
                                data['price'] = val
                                break
                    if data['price']:
                        break

                count += 1
                print(f"  [FANZA] {title[:25]}... ¥{data['price']}")

            except Exception as e:
                print(f"  [FANZA] 詳細取得失敗: {title[:20]} - {e}")
                count += 1

    except Exception as e:
        print(f"[FANZA] エラー: {e}")
        try:
            print(f"[FANZA DEBUG] タイトル: {page.title()}")
            print(f"[FANZA DEBUG] URL: {page.url}")
            # ページ内の一部HTMLをデバッグ出力
            body_text = page.inner_text('body')
            print(f"[FANZA DEBUG] ページテキスト先頭300文字: {body_text[:300]}")
        except:
            pass

    finally:
        context.close()

    print(f"[FANZA] 合計{len(fanza_data)}件取得完了")
    return fanza_data


def scrape_fanza_api(api_id, affiliate_id):
    """FANZA公式APIから取得"""
    if not api_id or not affiliate_id:
        return {}

    import requests
    print("[FANZA API] 取得開始")
    try:
        res = requests.get('https://api.dmm.com/affiliate/v3/ItemList', params={
            'api_id': api_id, 'affiliate_id': affiliate_id,
            'site': 'FANZA', 'service': 'digital', 'floor': 'doujin',
            'hits': 50, 'sort': 'rank', 'output': 'json',
        }, timeout=30)
        res.raise_for_status()
        data = res.json()
    except Exception as e:
        print(f"[FANZA API] 失敗: {e}")
        return {}

    items = {}
    for item in data.get('result', {}).get('items', []):
        title = item.get('title', '')
        price = item.get('prices', {}).get('price', '0')
        price = int(''.join(c for c in str(price) if c.isdigit()) or '0')
        items[title] = {'price': price, 'url': item.get('URL', '')}

    print(f"[FANZA API] {len(items)}件取得完了")
    return items


def match_titles(t1, t2):
    """タイトルの柔軟なマッチング"""
    def norm(t):
        return re.sub(r'[　\s～〜・！？!?\-\[\]【】「」『』（）()]+', '', t).lower()

    n1, n2 = norm(t1), norm(t2)
    if n1 == n2:
        return True
    shorter = n1 if len(n1) <= len(n2) else n2
    longer = n2 if len(n1) <= len(n2) else n1
    if len(shorter) >= 5 and shorter in longer:
        return True
    if len(n1) >= 8 and len(n2) >= 8 and n1[:8] == n2[:8]:
        return True
    return False


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # DLsite
        page = browser.new_page(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        dlsite_items = scrape_dlsite_ranking(page)
        page.close()

        # FANZA: APIキーがあればAPI、なければスクレイピング
        fanza_api_id = os.environ.get('FANZA_API_ID', '')
        fanza_affiliate_id = os.environ.get('FANZA_AFFILIATE_ID', '')

        if fanza_api_id and fanza_affiliate_id:
            fanza_data = scrape_fanza_api(fanza_api_id, fanza_affiliate_id)
        else:
            fanza_data = scrape_fanza_ranking(browser)

        browser.close()

    # マッチング
    matched = 0
    for item in dlsite_items:
        for ftitle, fdata in fanza_data.items():
            if match_titles(item['title'], ftitle):
                item['fanzaPrice'] = fdata.get('price')
                item['fanzaUrl'] = fdata.get('url', '')
                matched += 1
                break

    print(f"[マッチング] {matched}/{len(dlsite_items)}件がFANZAと一致")

    output = {
        'updatedAt': datetime.now().strftime('%Y/%m/%d %H:%M'),
        'source': 'DLsite + FANZA ' + ('API' if fanza_api_id else 'scraping'),
        'fanzaMethod': 'api' if fanza_api_id else 'scraping',
        'items': dlsite_items,
    }

    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n===== 完了 =====")
    print(f"DLsite: {len(dlsite_items)}件")
    print(f"FANZA: {len(fanza_data)}件")
    print(f"価格比較可能: {matched}件")


if __name__ == '__main__':
    main()
