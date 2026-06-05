# Sipariş Yerleştirme Optimizasyonu

Bu proje, oluklu mukavva fabrikası depolarında gelen siparişleri en uygun rafa yerleştirmek için geliştirilmiş bir karar destek uygulamasıdır.

## Hedef

- Tamamen kişiselleştirilebilir bir parametre yapısı sunar.
- Sipariş bilgisinden otomatik raf önerisi üretir.
- Sık kullanılan paket ölçülerini hazır liste olarak kaydedip sipariş formunda yeniden kullanır.
- Raf tiplerini sol menüden ekleyip silebilirsiniz.
- Seçili raf tipinin ölçü ve boşluk parametrelerini sol menüde ayrıca düzenleyebilirsiniz.
- Rafları adet değil, santimetre bazlı boş alan matrisi ile yönetir.
- Taşıyıcıya manuel müdahale imkanı verir (rafı dolu/açık işaretleme).
- Rafı tek tuşla tamamen boşaltma fonksiyonu sunar.
- Tüm rafları tek işlemde boşaltır ve işlem öncesi onay ister.
- Raf yönetiminde hızlı seçim alanlarıyla (A/S/R/Y) raf seçimini hızlandırır.
- 3B görselleştirme olmadan çekirdek optimizasyon problemini çözer.

## Girdi Verileri

Her sipariş için:

- Hazır paket ölçüsü seçimi veya yeni paket ölçüsü kaydı
- Siparişin palet üstü ölçüsü (genişlik, derinlik)
- Palet ölçüsü (genişlik, derinlik)
- Gideceği firma
- Sevk tarihi

## Arayüzden Değiştirilebilen Parametreler

- Koridor sayısı
- Koridor başına taraf sayısı
- Taraf başına sıra sayısı
- Sıra başına Y düzlemindeki raf adedi
- Raf ölçüleri (genişlik, derinlik, yükseklik)
- Güvenlik payları (genişlik, derinlik)
- Referans en küçük palet ölçüsü
- Döndürme izni
- Firma kümelendirme aç/kapat
- Sevk tarihi kümelendirme aç/kapat
- Tarih kümelendirme gün aralığı
- Çok kriterli skor ağırlıkları:
  - Doluluk verimi
  - Mesafe
  - Firma kümelendirme
  - Tarih kümelendirme
  - Dengeleme
- Öneri adedi
- Minimum kullanılabilir parça alanı

## Algoritma Özeti

1. Sipariş için efektif yerleşim ölçüsü hesaplanır:
   - max(sipariş ölçüsü, palet ölçüsü) + güvenlik payı
2. Her raf için uygun boş dikdörtgenler taranır.
3. Gerekirse döndürülmüş yerleşim de denenir.
4. Her aday için skor hesaplanır:
   - Düşük atık alan (iyi)
   - Kısa yol/mesafe (iyi)
   - Aynı firma ve yakın tarih kümelendirme (iyi)
   - Raf dengesi (aşırı tek raf yükünü azaltma)
5. En düşük skorlu raf seçilir ve sipariş yerleştirilir.
6. Yerleşim sonrası raf boş alanları guillotine split ile güncellenir.
7. Taşıyıcı isterse rafı manuel dolu işaretler; bu raf önerilerden çıkarılır.
8. Taşıyıcı isterse rafı tek tuşla boşaltır; raf tekrar kullanılabilir hale gelir.

## Çalıştırma

1. Bağımlılık yükle:

```bash
pip install -r requirements.txt
```

2. Uygulamayı başlat:

```bash
streamlit run app.py
```

## Dosya Yapısı

- `app.py`: Streamlit arayüzü
- `src/models.py`: Veri modelleri
- `src/engine.py`: Yerleştirme algoritması
- `src/storage.py`: JSON kalıcılık katmanı
- `data/state.json`: Uygulama durumu (ilk çalıştırmada oluşur)

## Notlar

- Topolojiyi (koridor/sıra/raf yapısı) değiştirirken yeniden kurulum seçeneği aktif edilirse eski yerleşimler temizlenir.
- Mevcut sürüm 2D alan optimizasyonu yapar. 3B görselleştirme ve dikey istif kuralları sonraki aşamaya bırakılmıştır.
