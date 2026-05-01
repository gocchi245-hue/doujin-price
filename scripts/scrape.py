import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'ja,en;q=0.9',
}

def scrape_dlsite_ranking():
    """DLsiteの同人ランキングページをスクレイピング"""
    url = 'https://www.dlsite.com/maniax/ranking/day'
    print(f"[DLsite] ランキング取得中: {url}")

    try:
        res = requests.get(url, headers=HEADERS, timeout=30)
        res.raise_for_status()
    except Exception as e:
        print(f"[DLsite] 取得失敗: {e}")
        return []

    soup = BeautifulSoup(res.text, 'html.parser')
    items = []
    rank = 0

    # ランキングの各作品を取得
    for work in soup.select('.n_worklist_item, .rank_list .n_worklist_item, table.n_worklist tr, .ranking_table tr, .work_1col_table tr'):
        rank += 1
        if rank > 30:
            break

        try:
            # タイトル
            title_el = work.select_one('a.work_name, dt.work_name a, .work_name a')
            if not title_el:
                rank -= 1
                continue
            title = title_el.get_text(strip=True)
            href = title_el.get('href', '')

            # product_id を抽出
            product_id = ''
            if '/product_id/' in href:
                product_id = href.split('/product_id/')[1].split('.')[0].split('/')[0]

            # サークル名
            circle_el = work.select_one('.maker_name a, .circle_name a, dd.maker_name a')
            circle = circle_el.get_text(strip=True) if circle_el else '不明'

            # 価格
            price_el = work.select_one('.work_price, .strike, .price')
            price_text = price_el.get_text(strip=True) if price_el else '0'
            price = int(''.join(c for c in price_text if c.isdigit()) or '0')

            # 元価格（セール時）
            orig_el = work.select_one('.work_price .strike, .normal_price')
            orig_price = None
            if orig_el:
                orig_text = orig_el.get_text(strip=True)
                orig_price = int(''.join(c for c in orig_text if c.isdigit()) or '0')
                if orig_price == price:
                    orig_price = None

            # ジャンルタグ
            tags = []
            for tag_el in work.select('.search_tag a, .work_genre a, .genre a'):
                tags.append(tag_el.get_text(strip=True))

            # 評価
            star_el = work.select_one('.star_rating, .point .average, .review_point')
            rating = None
            if star_el:
                star_text = star_el.get_text(strip=True)
                try:
                    rating = float(''.join(c for c in star_text if c.isdigit() or c == '.') or '0')
                    if rating > 5:
                        rating = rating / 10 if rating <= 50 else None
                except:
                    pass

            # URL構築
            if product_id:
                dlsite_url = f"https://www.dlsite.com/maniax/work/=/product_id/{product_id}.html"
            elif href.startswith('http'):
                dlsite_url = href
            else:
                dlsite_url = f"https://www.dlsite.com{href}" if href else ''

            # ジャンル推定
            genre = 'その他'
            genre_map = {
                'RPG': ['RPG', 'ロールプレイング'],
                '音声': ['音声', 'ASMR', 'ボイス', 'バイノーラル'],
                'CG集': ['CG', 'イラスト', 'CG集'],
                'ノベル': ['ノベル', 'ADV', 'アドベンチャー'],
                'マンガ': ['マンガ', '漫画', 'コミック'],
                'アクション': ['アクション', 'ACT'],
                'シミュレーション': ['シミュレーション', 'SLG'],
            }
            title_lower = title.lower()
            for g, keywords in genre_map.items():
                for kw in keywords:
                    if kw.lower() in title_lower or kw in tags:
                        genre = g
                        break

            # 絵文字
            emoji_map = {'RPG':'⚔️','音声':'🎵','CG集':'🎨','ノベル':'📖','マンガ':'📚','アクション':'🎮','シミュレーション':'🏰','その他':'📄'}
            emoji = emoji_map.get(genre, '📄')

            items.append({
                'rank': rank,
                'title': title,
                'circle': circle,
                'genre': genre,
                'price': price,
                'originalPrice': orig_price,
                'tags': tags[:3],
                'dlsiteUrl': dlsite_url,
                'productId': product_id,
                'rating': rating,
                'emoji': emoji,
                'isOnSale': orig_price is not None and orig_price > price,
            })
        except Exception as e:
            print(f"[DLsite] 作品パース失敗 (rank {rank}): {e}")
            rank -= 1
            continue

    print(f"[DLsite] {len(items)}件取得完了")
    return items


def scrape_fanza_api(api_id, affiliate_id):
    """FANZA APIから同人作品を取得"""
    if not api_id or not affiliate_id:
        print("[FANZA] APIキー未設定 - スキップ")
        return {}

    url = 'https://api.dmm.com/affiliate/v3/ItemList'
    params = {
        'api_id': api_id,
        'affiliate_id': affiliate_id,
        'site': 'FANZA',
        'service': 'digital',
        'floor': 'doujin',
        'hits': 50,
        'sort': 'rank',
        'output': 'json',
    }

    print(f"[FANZA] API取得中")
    try:
        res = requests.get(url, params=params, headers=HEADERS, timeout=30)
        res.raise_for_status()
        data = res.json()
    except Exception as e:
        print(f"[FANZA] 取得失敗: {e}")
        return {}

    fanza_items = {}
    for item in data.get('result', {}).get('items', []):
        title = item.get('title', '')
        price_info = item.get('prices', {})
        price = price_info.get('price', '0')
        price = int(''.join(c for c in str(price) if c.isdigit()) or '0')

        fanza_url = item.get('URL', '')
        fanza_items[title] = {
            'price': price,
            'url': fanza_url,
        }

    print(f"[FANZA] {len(fanza_items)}件取得完了")
    return fanza_items


def merge_data(dlsite_items, fanza_items):
    """DLsiteとFANZAのデータをマージ"""
    merged = []
    for item in dlsite_items:
        # FANZAから同名作品を検索（簡易マッチ）
        fanza_price = None
        fanza_url = ''
        for ftitle, fdata in fanza_items.items():
            # タイトルの部分一致で検索
            if item['title'] in ftitle or ftitle in item['title']:
                fanza_price = fdata['price']
                fanza_url = fdata['url']
                break

        item['fanzaPrice'] = fanza_price
        item['fanzaUrl'] = fanza_url
        merged.append(item)

    return merged


def main():
    # DLsiteランキング取得
    dlsite_items = scrape_dlsite_ranking()

    # FANZA API取得（環境変数からキーを読む）
    fanza_api_id = os.environ.get('FANZA_API_ID', '')
    fanza_affiliate_id = os.environ.get('FANZA_AFFILIATE_ID', '')
    fanza_items = scrape_fanza_api(fanza_api_id, fanza_affiliate_id)

    # データマージ
    merged = merge_data(dlsite_items, fanza_items)

    # JSON保存
    output = {
        'updatedAt': datetime.now().strftime('%Y/%m/%d %H:%M'),
        'source': 'DLsite ranking + FANZA API',
        'items': merged,
    }

    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\ndata.json に{len(merged)}件保存しました")
    print(f"更新日時: {output['updatedAt']}")


if __name__ == '__main__':
    main()
