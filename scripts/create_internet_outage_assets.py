from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import edge_tts
from mutagen.mp3 import MP3


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "motion" / "public" / "internet-outage"
OUTPUT = ROOT / "output" / "internet-outage"
TTS_CACHE = OUTPUT / "tts-cache"


CHAPTERS = [
    {
        "id": "hook",
        "title": "08.17 — Türkiye çevrim dışı",
        "sentences": [
            "Saat sabah sekiz on yedi.",
            "Telefonunuzda internet yok, modem kırmızı yanıyor ve aynı soru milyonlarca evde soruluyor: sorun bende mi?",
            "Hayır; Türkiye'nin dış dünyaya açılan internet bağlantısı kesildi.",
            "Mesajlar gitmiyor, haritalar yeni yol indiremiyor, kart terminali cevap bekliyor.",
            "Ama şehir karanlığa gömülmedi, uçaklar düşmedi ve banka hesaplarındaki para yok olmadı.",
            "Çünkü internet, elektrik ve telefon şebekesi aynı şey değil.",
            "Şimdi ilk dakikadan gece yarısına kadar; ödemelerin, yüz on ikinin, GPS'in ve marketlerin başına ne geldiğini saat saat yaşayacağız.",
        ],
    },
    {
        "id": "rules",
        "title": "Senaryonun kuralları",
        "sentences": [
            "Önce senaryoyu doğru kuralım; çünkü tek bir kablonun kopması bütün ülkeyi çevrim dışı bırakmaz.",
            "Türkiye, Avrupa ve Asya arasında birden fazla kara fiber hattıyla ve denizaltı bağlantısıyla dünyaya bağlı.",
            "İnternetin tasarımı, bir yol kapandığında trafiği başka yola çevirmeye çalışır.",
            "Gerçek bir ülke çapı kesinti için aynı anda birden fazla şeyin ters gitmesi gerekir: ana yönlendirme sistemleri, büyük veri merkezleri, omurga bağlantıları veya bunları besleyen enerji ve yönetim altyapısı.",
            "Bizim deneyimizde yurt dışı internet çıkışları ve büyük ulusal omurgalar ağır biçimde bozuluyor.",
            "Ev ve mobil internetin çoğu çalışmıyor; fakat elektrik şebekesi başlangıçta ayakta.",
            "Geleneksel telefon görüşmesi ve kısa mesaj için kullanılan mobil çekirdek sistemlerin bir bölümü çalışmayı sürdürüyor.",
            "Kurumların kendi özel ağları, kapalı devre sistemleri ve yerel sunucuları da sihirli biçimde yok olmuyor.",
            "Bu ayrım önemli.",
            "İnternet, dünyadaki bütün bilgisayarların tek bir düğmeye bağlı olduğu dev bir makine değil; birbirine bağlanan binlerce ağın ortak trafiği.",
            "Dolayısıyla sonuç, her ekranın aynı saniyede kapanması değil.",
            "Daha çok büyük bir şehrin bütün ana yolları kapanmışken ara sokaklarda hâlâ hareket etmeye çalışmaya benziyor.",
            "Bazı yerel hizmetler nefes alır, bazıları dışarıdaki tek bir doğrulama sunucusuna erişemediği için anında donar.",
            "Saat başlıyor.",
        ],
    },
    {
        "id": "first_minutes",
        "title": "İlk 15 dakika",
        "sentences": [
            "İlk on beş dakikada yaşanan en büyük şey teknik arızadan çok toplu bir refleks.",
            "Herkes aynı anda kablosuz ağı kapatıyor, mobil veriye geçiyor ve ekranın köşesindeki çekim çubuklarına bakıyor.",
            "Çubuklar yerinde olabilir; çünkü telefonunuz baz istasyonunu hâlâ görüyor.",
            "Ama baz istasyonuna bağlanmak, internet üzerindeki hedefe ulaşabildiğiniz anlamına gelmez.",
            "Bir binanın kapısına kadar gelip içerideki asansörün çalışmadığını görmek gibi.",
            "Mesajlaşma uygulamaları gönderiliyor işaretinde kalır, sosyal medya akışı yenilenmez, bulut belgeleri açılmaz.",
            "Daha önce indirdiğiniz müzik, film, fotoğraf ve dosyalar ise telefonunuzda durur.",
            "Bazı uygulamalar önbelleğe alınmış eski sayfaları gösterir; bu yüzden birinin ekranı birkaç dakika normal görünürken diğerininki tamamen boş olabilir.",
            "Evdeki akıllı ampulün davranışı bile markasına göre değişir.",
            "Yerel ağ üzerinden çalışan cihaz açılabilir; her komutu uzaktaki buluta gönderen cihazsa internet gelene kadar akıllılığını kaybeder.",
            "Ofislerde ilk toplantı iptal olur, ama asıl panik şirket içi dosyaların dışarıdaki bulut sistemlerinde olduğu anlaşılınca başlar.",
            "İnsanlar operatörlerin çağrı merkezlerini aramaya yönelir.",
            "Tam bu noktada çalışan telefon şebekesinin kapasitesi sınanır; çünkü bir baz istasyonu aynı anda sınırsız kişiye hizmet veremez.",
            "BTK'nın da açıkladığı gibi kapsama başka, kapasite başka meseledir.",
            "Ekranda sinyal gördüğünüz hâlde aramanızın ilk denemede bağlanmaması mümkündür.",
            "Ve henüz yalnızca on beş dakika geçti.",
        ],
    },
    {
        "id": "inside_turkiye",
        "title": "Türkiye'nin içinde ne kalır?",
        "sentences": [
            "Yarım saate yaklaşırken garip bir durum fark edilir: aynı binadaki iki bilgisayar birbiriyle konuşabilirken dışarıdaki siteye ulaşamaz.",
            "Çünkü yerel ağınızın çalışması için her paketin yurt dışına gitmesi gerekmez.",
            "Evde bilgisayardan ağ yazıcısına belge göndermek, modemin internet ışığı kırmızı olsa bile mümkün olabilir.",
            "Bir şirketin kendi binasındaki dosya sunucusu ve personel sistemi de yerel tasarlanmışsa çalışmayı sürdürebilir.",
            "Fakat oturum açma işlemi dışarıdaki bir kimlik hizmetine bağlıysa kapının anahtarı uzakta kalmış demektir.",
            "Dosya odanın içinde durur, kullanıcı ona erişemez.",
            "Aynı ayrım web sitelerinde de vardır.",
            "Bir hizmetin görüntüleri Türkiye'deki önbellek sunucularında bulunabilir; ama hesap doğrulaması, reklam sistemi veya veri tabanı başka bir ülkedeyse sayfa yarım açılır.",
            "Logo gelir, video gelmez; başlık görünür, yorumlar sonsuza kadar yüklenir.",
            "İnternet adreslerini isimle bulmamızı sağlayan alan adı sistemi de önemlidir.",
            "Telefon rehberi gibi çalışan bu sistem hedefin sayısal adresini çeviremezse sunucu ayakta olsa bile tarayıcı siteyi bulamayabilir.",
            "Daha önce öğrenilmiş adresler cihazların belleğinde bir süre kalabilir, fakat bu kayıtların süresi doldukça çalışan küçük adacıklar da kaybolur.",
            "Türkiye içindeki iki ağın birbirine hangi yoldan ulaştığı da sonucu değiştirir.",
            "Trafik yerel bir bağlantıdan geçebiliyorsa hizmet yaşayabilir; gereksiz biçimde yurt dışındaki bir noktaya çıkıp geri dönüyorsa kesintiye yakalanır.",
            "Bu yüzden ülke çapı internet arızası siyah beyaz bir ekran üretmez.",
            "Haritada birbirinden kopuk, bazıları çalışan bazıları donmuş dijital adalar bırakır.",
            "İlk yarım saatin sonunda teknik ekiplerin en önemli sorusu internet var mı değil, hangi ağa hangi yoldan ulaşılabiliyor olur.",
        ],
    },
    {
        "id": "payments",
        "title": "İlk saat — ödeme duvarı",
        "sentences": [
            "Kesintinin ilk saati, internetin görünmez olduğu kadar ekonomik bir altyapı olduğunu gösterir.",
            "Bir müşteri kahvesini alır, kartını terminale dokundurur ve bekler.",
            "POS cihazı çoğu işlemde bankaya veya ödeme ağına ulaşıp kartı, limiti ve işlemi doğrulamak ister.",
            "İş yerinin bağlantısı kesilmişse bu konuşma gerçekleşmeyebilir.",
            "Ama bütün kartlar aynı anda ve her yerde kesin olarak ölür demek de yanlış.",
            "Bazı terminaller mobil hat, sabit hat veya özel kurumsal bağlantı kullanır; bazı düşük riskli işlemler belirli kurallarla çevrim dışı kabul edilebilir.",
            "Bankaların, büyük marketlerin ve ödeme kuruluşlarının yedek hatları olabilir.",
            "Sorun, kesinti ülke çapındaysa yedek bağlantının da aynı bozulan omurgaya çıkabilmesi.",
            "Bir kasada kart geçerken yan kasada geçmemesi bu yüzden şaşırtıcı olmaz.",
            "Kasa görevlisinin POS cihazına iki kez vurmasıysa teknik protokol değildir; sadece insanlığın ortak arıza giderme geleneğidir.",
            "Mobil bankacılık ve internet bankacılığı kullanıcıya ulaşamadığı için FAST ya da havale emri veremezsiniz.",
            "Merkezdeki ödeme sistemleri çalışsa bile sizin telefonunuzdan bankanıza giden yol kapalı olabilir.",
            "ATM'ler de tek tip değildir.",
            "Banka ağına erişebilen bir ATM çalışmayı sürdürebilir; bağlantısını kaybeden cihaz güvenlik nedeniyle işlem vermeyi durdurabilir.",
            "Haber yayıldıkça nakit çekmek isteyenlerin sayısı artar ve çalışan ATM'lerin içindeki banknotlar hızla azalır.",
            "Marketler nakit kabul eder, fakat para üstü kısa sürede yeni bir probleme dönüşür.",
            "Bir saatlik kesinti ekonomik sistemi yok etmez; yine de günlük hayatın ne kadarının anlık doğrulamaya bağlı olduğunu görünür kılar.",
        ],
    },
    {
        "id": "maps_transport",
        "title": "1–3 saat — şehir yönünü kaybediyor",
        "sentences": [
            "İkinci saate girerken şehir hareket etmeye devam eder, ama koordinasyonu bozulur.",
            "Burada en çok karıştırılan sistem GPS'tir.",
            "GPS uyduları uzaydan tek yönlü zaman ve konum sinyali yayınlamaya devam eder; Türkiye'nin internetinin kesilmesi bu uyduları kapatmaz.",
            "Telefonunuz açık gökyüzü altında konumunu hâlâ hesaplayabilir.",
            "Fakat harita uygulamasının yeni bölgeyi indirmesi, adres araması, canlı trafik bilgisi ve en hızlı rota hesabı sunucu bağlantısı isteyebilir.",
            "Yani mavi nokta çalışır, çevresindeki dünya eksik kalabilir.",
            "Haritayı önceden çevrim dışı indiren kişi yolunu bulur; yalnızca canlı trafik verisini kullanan sürücü kalabalığın içine girer.",
            "Taksi ve yolculuk uygulamaları sürücüyle müşteriyi eşleştiremez.",
            "Yemek ve market siparişleri mutfakta hazırlanmış olsa bile kurye ataması, adres doğrulama ve ödeme kaydı takılabilir.",
            "Toplu taşıma araçları fiziksel olarak çalışabilir, fakat mobil bilet, yolcu bilgilendirme ekranı ve merkezî takip sistemlerinin bir kısmı aksar.",
            "İstanbul, Ankara ve İzmir gibi büyük şehirlerde sabah trafiğine bir de navigasyonsuz kalan sürücüler eklenir.",
            "Akıllı kavşakların yerel programları çalışmayı sürdürebilir; uzaktan güncellenen sistemler sabit plana döner veya operatör müdahalesi ister.",
            "Havalimanlarında uçuş güvenliğinin temel sistemleri genel internetten ibaret değildir.",
            "Uçaklar sırf sosyal medya açılmıyor diye gökten düşmez.",
            "Ancak biletleme, çevrim içi check-in, ekip planlama, yolcu mesajları ve uluslararası veri alışverişi yavaşladıkça gecikmeler büyür.",
            "İnternet ulaşımı durdurmaz; ulaşımın senkronunu bozar.",
        ],
    },
    {
        "id": "communication",
        "title": "3–6 saat — arama var, kapasite yok",
        "sentences": [
            "Üçüncü saatten sonra insanlar mesaj uygulamalarının dönmeyeceğini kabul eder ve klasik telefon görüşmesine yüklenir.",
            "Bu, çalışan mobil şebeke için ikinci bir dalgadır.",
            "Baz istasyonunun kapsama alanında olmak size bir kapı gösterir, fakat aynı kapıdan binlerce kişi geçmeye çalışırsa aramalar başarısız olabilir.",
            "Kısa mesaj, veri miktarı küçük olduğu için yoğunlukta bazen görüşmeden daha kolay ilerler; fakat o da sınırsız değildir.",
            "Aileler birbirini arar, şirketler çalışanlarına ulaşmaya çalışır, bankalar ve operatörler durum mesajları gönderir.",
            "Bu yüzden acil olmayan aramaları azaltmak yalnızca nazik bir davranış değil, kapasiteyi gerçekten acil ihtiyaca bırakmaktır.",
            "Peki yüz on iki?",
            "Yüz on iki çağrısı bir sosyal medya uygulaması gibi genel internet üzerinden çalışmaz.",
            "Sabit veya mobil telefon altyapısı ayaktaysa ücretsiz arama yapılabilir; resmî bilgiye göre SIM kart olmadan bile yüz on iki aranabilir.",
            "Konuşamayacak durumda olanlar yüz on ikiye ücretsiz kısa mesaj da gönderebilir, ancak resmî uyarı nettir: mümkünse aramak daha hızlı ve güvenilirdir.",
            "Yine de internet kesintisiyle birlikte mobil çekirdek ağ, baz istasyonu bağlantıları veya enerji de zarar gördüyse acil arama erişimi bölgesel olarak bozulabilir.",
            "Yani doğru cümle, yüz on iki kesin çalışır ya da kesin çalışmaz değildir.",
            "Doğru cümle şudur: genel internetin gitmesi yüz on ikiyi doğrudan kapatmaz, fakat telefon şebekesinin kapasitesi ve ayakta kalması belirleyicidir.",
            "Bu ayrım videolarda küçük görünür, gerçek hayatta hayati önem taşır.",
        ],
    },
    {
        "id": "news",
        "title": "6–9 saat — bilgi boşluğu",
        "sentences": [
            "Altıncı saatte teknik kesintinin yanına bir bilgi krizi eklenir.",
            "İnsanlar arızanın nedenini, ne kadar süreceğini ve yalnızca kendi şehirlerini mi etkilediğini bilmek ister.",
            "Sosyal medya yoksa söylenti yok olmaz; sadece daha yavaş ve kontrol edilmesi daha zor kanallara taşınır.",
            "Bir apartmanda duyulan cümle birkaç telefon görüşmesi sonra başka bir şehirde resmî açıklama gibi anlatılabilir.",
            "Televizyon ve radyo yayınları ise internetle aynı sistem değildir.",
            "Karasal verici, uydu yayını ve geleneksel radyo altyapısı ayaktaysa haber vermeye devam edebilir.",
            "Yayın kuruluşlarının haber toplama ve uzak ekiplerle iletişim tarafı zorlaşsa da stüdyodan temel duyuru yapılabilir.",
            "Bu nedenle pilli veya araç radyosu, akıllı telefondan daha akıllı bir cihaza dönüşür.",
            "Kamu kurumları kısa mesaj, radyo, televizyon, araç anonsu ve fiziksel duyuru gibi kanalları birlikte kullanmaya başlar.",
            "Sorun, milyonlarca kişinin aynı açıklamayı aynı anda doğrulayamamasıdır.",
            "Eski ekran görüntüleri yeni olaymış gibi telefonlar arasında gösterilir, nedeni bilinmeyen kesinti siber saldırı, savaş veya deprem söylentisine dönüşebilir.",
            "Burada en tehlikeli içerik en korkunç olan değil, tanıdığınız birinden geldiği için doğru sandığınızdır.",
            "Resmî yayınlarda saat, kaynak ve tekrar edilen net talimatlar kritik hâle gelir.",
            "İnternet bilgiye erişimi hızlandırıyordu; şimdi güvenilir bilgiyi diğerinden ayırmanın maliyeti yükselir.",
        ],
    },
    {
        "id": "logistics",
        "title": "9–12 saat — rafların arkasındaki ağ",
        "sentences": [
            "Dokuzuncu saatte market rafları bir anda boşalmaz; fakat rafların arkasındaki görünmez ağ yavaşlamaya başlar.",
            "Modern lojistik yalnızca kamyon ve depodan oluşmaz.",
            "Sipariş, stok, rota, sürücü görevi, teslimat kanıtı ve fatura bilgisi sürekli sistemler arasında dolaşır.",
            "Büyük şirketlerin özel ağları ve yerel yazılımları bazı işleri sürdürebilir.",
            "Küçük işletmeler bulut tabanlı stok programına erişemediğinde eldeki ürünü kâğıda yazmaya döner.",
            "Depodaki palet fiziksel olarak oradadır; sistemde hangi mağazaya ayrıldığını görmek zorlaşır.",
            "Akaryakıt istasyonlarında pompa çalışabilir, ancak ödeme, merkezî fiyat, stok takibi ve tanker planlaması bağlantıya bağlıysa satış yavaşlar.",
            "Her istasyonun aynı anda kapanacağını söylemek doğru değildir; altyapı ve yedek plan farklıdır.",
            "Fakat sürücüler depo doldurmaya yönelirse asıl darboğaz yakıtın yokluğu değil, istasyonun ödeme ve hizmet kapasitesi olur.",
            "Eczanelerde de benzer bir tablo çıkar.",
            "İlaç rafı yerindedir; reçete doğrulama, geri ödeme ve hasta kaydı gibi çevrim içi adımlar aksayabilir.",
            "Acil ihtiyaçlar için kurumların kesinti prosedürleri devreye girer, rutin işlemler ertelenir ve kayıtlar daha sonra sisteme işlenmek üzere tutulur.",
            "On ikinci saate yaklaşırken şehir hâlâ çalışır, ama daha fazla insan karar vermek için ekrana değil telefona, kâğıda ve yüz yüze iletişime dönmüştür.",
        ],
    },
    {
        "id": "critical",
        "title": "12–16 saat — hastane, banka ve kamu",
        "sentences": [
            "Öğleden sonra kesintinin en hassas bölümü başlar: kritik kurumların yedekleri uzun süreli sınava girer.",
            "Bir hastanedeki ameliyathane cihazı, monitör veya oksijen sistemi normalde genel internete bağlı olmak zorunda değildir.",
            "Hastanelerin yerel ağları, jeneratörleri ve kesinti planları kritik hizmetleri sürdürmek için tasarlanır.",
            "Ama hastane yalnızca ameliyathaneden oluşmaz.",
            "Merkezî randevu, e-reçete, dış laboratuvar sonucu, başka hastaneyle görüntü paylaşımı, personel iletişimi ve tedarik siparişi aksadıkça iş yükü büyür.",
            "Doktorlar acil hastaya bakmaya devam eder; kayıt ve koordinasyon daha yavaş, daha elle ve daha hataya açık hâle gelir.",
            "Bankaların merkezleri de özel hatlar, yedek veri merkezleri ve iş sürekliliği planları kullanır.",
            "Bu yüzden internet kesildi diye hesap bakiyeleri silinmez.",
            "Ancak şube, ATM, iş yeri ve müşteri arasındaki bağlantı koptuğunda paraya erişmek farklı bir sorun olur.",
            "Kamu kurumlarında kapalı ağlar çalışan bazı servisleri ayakta tutabilir; vatandaşa açık internet portalları ve dış bağlantılı işlemler bekler.",
            "Limanlar ve havaalanları güvenlik açısından yerel ve özel sistemlere dayanır, fakat uluslararası evrak ve lojistik veri akışı yavaşladığında kuyruk uzar.",
            "Buradaki ortak desen şudur: kritik sistem hemen çökmez; bağlantısız kaldıkça çevresindeki destek halkaları zayıflar.",
            "Yedek planın değeri, ilk beş dakikada değil on beşinci saatte anlaşılır.",
        ],
    },
    {
        "id": "evening",
        "title": "16–20 saat — şehir yavaşlıyor",
        "sentences": [
            "Akşam olduğunda Türkiye ilk kez internetsiz bir iş gününün bilançosunu görür.",
            "Evine dönenler mesaj gönderemediği için buluşma noktaları eski usule döner.",
            "Restoranlar çevrim içi sipariş alamaz, bazıları yalnızca nakit çalışır, bazıları stok ve ödeme belirsizliği yüzünden erken kapanır.",
            "Apartman girişindeki bulut tabanlı kamera uygulaması açılmayabilir; yerel kayıt cihazı görüntüyü kaydetmeye devam edebilir.",
            "Akıllı televizyon çevrim içi platforma ulaşamaz, ama anten veya uydu yayını çalışır.",
            "Çocukların daha önce indirilmiş oyunları açılır; her açılışta lisans doğrulaması isteyen oyunlar açılmaz.",
            "Ofislerde gün içinde kâğıda alınan siparişler, notlar ve telefon mesajları birikir.",
            "İnternet geri geldiğinde hepsinin sisteme doğru sırayla girilmesi gerekecektir.",
            "Asıl risklerden biri, çalışanların bağlantı gelsin diye telefonlarını tanımadıkları kablosuz ağlara ve sahte destek mesajlarına açmasıdır.",
            "Kesinti anı dolandırıcı için de fırsattır; bankanızmış gibi arayıp şifre isteyen kişi internetin yokluğundan yararlanır.",
            "Şehir tamamen sessiz değildir.",
            "Telefon görüşmeleri, radyo, televizyon, telsiz, özel ağlar ve yüz yüze iletişim sürer; fakat gündelik hayatın ritmi gözle görülür biçimde düşer.",
            "İnternetin yaptığı şey yalnızca bilgi taşımak değildi.",
            "İnsanların ve makinelerin aynı anda aynı kayda bakmasını sağlıyordu.",
        ],
    },
    {
        "id": "night",
        "title": "20–24 saat — ikinci gün korkusu",
        "sentences": [
            "Gece yarısına yaklaşırken ilk günün paniği yerini ikinci günün hesabına bırakır.",
            "Yirmi dört saatlik kesinti Türkiye'yi Taş Devri'ne göndermez; elektrik, su, yollar ve çalışan yerel sistemler hâlâ vardır.",
            "Ama kesinti birkaç gün daha sürerse sorunların şekli değişir.",
            "Yakıt ve ilaç dağıtımındaki gecikmeler büyür, işletmeler nakit ve kayıt sorunu yaşar, küçük firmalar sipariş zincirini kaybeder.",
            "Veri merkezleri kendi enerjilerini ve bağlantılarını uzun süre korumak zorunda kalır.",
            "Mobil şebeke ekipleri arızalı omurgayı atlamak için geçici radyolink, uydu bağlantısı ve taşınabilir istasyon kurmaya çalışır.",
            "Trafik önce acil kurumlara, bankalara, operatörlere ve büyük hizmet sağlayıcılara öncelik verilerek parça parça geri dönebilir.",
            "Bu nedenle internetin geri gelişi tek bir anda bütün telefonların normale dönmesi gibi görünmeyebilir.",
            "Bir şehir bağlanırken diğeri bekleyebilir; bir operatörde veri açılırken diğerinde yalnızca arama çalışabilir.",
            "Bağlantı gelir gelmez milyonlarca telefon, uygulama ve bilgisayar aynı anda güncelleme ve mesaj göndermeye çalışır.",
            "Bu ani yük, kurtarılan sistemi yeniden zorlayabilir.",
            "Dün gönderilmeyen mesajlar sırayla düşer, banka bildirimleri gecikmeli gelir ve şirket sunucuları bir günlük kuyruğu işlemeye başlar.",
            "Yani kesintinin son dakikası, bütün sorunların son dakikası değildir.",
        ],
    },
    {
        "id": "cause_recovery",
        "title": "Bu gerçekten nasıl olabilir?",
        "sentences": [
            "Peki böyle bir olay gerçek dünyada nasıl yaşanabilir?",
            "En sinematik cevap denizaltı kablolarının kesilmesi, ama tek başına bu genellikle yeterli değildir.",
            "RIPE ağ ölçümlerinde de görüldüğü gibi kablo hasarında trafik çoğu zaman başka güzergâhlara yönelir; gecikme artabilir ama bağlantı tamamen kaybolmayabilir.",
            "Türkiye'nin Avrupa'ya kara fiberleri ve bölgesel denizaltı bağlantıları bulunur.",
            "Ülke çapında ağır kesinti; eş zamanlı kablo hasarı, yanlış yönlendirme duyuruları, büyük enerji sorunu, veri merkezi arızası veya koordineli siber saldırı gibi birden fazla katmanın birlikte bozulmasını gerektirir.",
            "Bazen fiziksel altyapı sağlamken bir yönlendirme hatası ağların birbirini bulmasını engelleyebilir.",
            "Bazen alan adı sistemi bozulur ve bilgisayarlar hedefin sayısal adresini bilmedikleri için site yokmuş gibi görünür.",
            "Bazen de hizmetin kendisi çalışır, fakat onu kullanan kimlik doğrulama veya bulut servisi çöker.",
            "Onarım ekipleri önce arızanın hangi katmanda olduğunu ayırır.",
            "Fiber mi koptu, enerji mi yok, cihaz mı arızalı, yanlış rota mı yayınlandı, yoksa saldırı trafiği mi var?",
            "Ardından güvenli yedek yapı devreye alınır, rotalar kontrollü biçimde açılır ve ölçüm noktalarından kayıp ile gecikme izlenir.",
            "En hızlı görünen çözümü düşünmeden uygulamak yeni bir arıza yaratabilir; bu yüzden geri dönüş kademeli olur.",
            "Maskotumuzun bütün fişleri çıkarıp yeniden takma önerisi bu ölçekte maalesef kabul edilmedi.",
        ],
    },
    {
        "id": "survival",
        "title": "Bir gün için ne gerekir?",
        "sentences": [
            "Bu senaryoda sıradan bir insanın yapabileceği şey şaşırtıcı biçimde basit.",
            "Önce kesintiyi elektrik arızası sanıp bütün cihazları tekrar tekrar kurcalamak yerine operatör duyurusunu radyo, televizyon veya kısa mesajdan takip edin.",
            "Telefonun pilini koruyun; ekran parlaklığını düşürün, arka plandaki uygulamaları kapatın ve gereksiz arama yapmayın.",
            "Ailenizle önceden belirlenmiş bir buluşma noktası ve şehir dışından ortak bir irtibat kişisi seçin.",
            "Önemli telefon numaralarını yalnızca bulutta değil kâğıtta da tutun.",
            "Yaşadığınız bölgenin çevrim dışı haritasını önceden indirin.",
            "Evde makul miktarda nakit bulundurun; fakat kesinti anında herkesle yarışıp bütün paranızı çekmeye çalışmak sistemi daha hızlı kilitler.",
            "Pilli radyo, şarjlı güç bankası, fener, temel ilaç ve içme suyu yalnız internet kesintisinde değil birçok acil durumda işe yarar.",
            "Tanımadığınız birinin arayıp banka şifresi, doğrulama kodu veya kart bilgisi istemesine güvenmeyin.",
            "Yüz on ikiyi yalnız gerçek acil durumda arayın ve konuşamayacaksanız ilk kısa mesaja konumla olayın ne olduğunu açıkça yazın.",
            "En önemlisi, duyduğunuz her söylentiyi yaymayın.",
            "İnternet olmadığında yanlış bilgi yavaş yayılır sanabiliriz; oysa doğrulama zorlaştığı için daha uzun yaşayabilir.",
        ],
    },
    {
        "id": "outro",
        "title": "Sonuç",
        "sentences": [
            "Yirmi dört saat sonunda gördüğümüz şey, internetin hayatımızdaki tek sistem olmadığı ama neredeyse bütün sistemler arasındaki görünmez bağ olduğudur.",
            "Elektrik varken ışıklar yanar, GPS uyduları konum göndermeye devam eder, bazı telefon görüşmeleri ve yerel ağlar çalışır.",
            "Fakat ödeme, ulaşım, sağlık, lojistik ve haberleşme aynı gün içinde yavaş yavaş ortak ritmini kaybeder.",
            "Gerçek tehlike, bir uygulamanın açılmaması değil; milyonlarca küçük kararın güncel ve ortak bilgi olmadan verilmesidir.",
            "İyi hazırlanmış kurumlar yedek ağlarla zamanı satın alır.",
            "İyi hazırlanmış insanlar da pil, nakit, çevrim dışı harita ve doğru iletişim planıyla paniği azaltır.",
            "İnternet geri geldiğinde ilk yapacağınız şey ne olurdu?",
            "Mesajlara mı bakardınız, bankayı mı kontrol ederdiniz, yoksa maskotumuz gibi modeme zafer konuşması mı yapardınız?",
            "Bir sonraki deney için iki seçeneğimiz var: Türkiye'de elektrik yirmi dört saat kesilse ne olur, yoksa bütün GPS uyduları bir günlüğüne sussa ne olur?",
            "Yorumlarda seçin.",
        ],
    },
]


async def main() -> None:
    PUBLIC.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    TTS_CACHE.mkdir(parents=True, exist_ok=True)
    tracks: list[tuple[Path, list[dict[str, int | str]], int]] = []
    sentence_index = 0
    for chapter_index, chapter in enumerate(CHAPTERS):
        for sentence in chapter["sentences"]:
            cache_key = hashlib.sha1(sentence.encode("utf-8")).hexdigest()[:16]
            path = TTS_CACHE / f"sentence_{cache_key}.mp3"
            boundary_path = TTS_CACHE / f"sentence_{cache_key}.json"
            boundaries: list[dict[str, int | str]] = []
            if path.exists() and boundary_path.exists():
                boundaries = json.loads(boundary_path.read_text(encoding="utf-8"))
            else:
                communicator = edge_tts.Communicate(
                    text=sentence,
                    voice="tr-TR-EmelNeural",
                    rate="+7%",
                    pitch="+1Hz",
                    volume="+0%",
                    boundary="WordBoundary",
                )
                with path.open("wb") as audio_file:
                    async for event in communicator.stream():
                        if event.get("type") == "audio":
                            audio_file.write(event["data"])
                        elif event.get("type") == "WordBoundary":
                            start_ms = round(int(event["offset"]) / 10_000)
                            duration_ms = max(70, round(int(event["duration"]) / 10_000))
                            boundaries.append({"text": str(event["text"]), "startMs": start_ms, "endMs": start_ms + duration_ms})
                boundary_path.write_text(json.dumps(boundaries, ensure_ascii=False), encoding="utf-8")
            tracks.append((path, boundaries, chapter_index))
            sentence_index += 1

    captions: list[dict[str, int | float | str | None]] = []
    words: list[dict[str, int | str]] = []
    ranges = [{"id": chapter["id"], "title": chapter["title"], "startMs": None, "endMs": None} for chapter in CHAPTERS]
    cursor_ms = 0
    chapter_audio: list[Path] = []
    for chapter_index, _chapter in enumerate(CHAPTERS):
        chapter_items = [(path, boundaries) for path, boundaries, index in tracks if index == chapter_index]
        chapter_command = ["ffmpeg", "-y"]
        chapter_filters: list[str] = []
        for local_index, (path, boundaries) in enumerate(chapter_items):
            if not boundaries:
                raise RuntimeError(f"Missing word boundaries for {path.name}")
            chapter_command.extend(["-i", str(path)])
            first_ms = int(boundaries[0]["startMs"])
            last_ms = int(boundaries[-1]["endMs"])
            gap_ms = 420 if local_index == len(chapter_items) - 1 else 190
            chapter_filters.append(
                f"[{local_index}:a]atrim=start={first_ms/1000:.3f}:end={(last_ms+105)/1000:.3f},"
                f"asetpts=PTS-STARTPTS,apad=pad_dur={gap_ms/1000:.3f}[s{local_index}]"
            )
            if ranges[chapter_index]["startMs"] is None:
                ranges[chapter_index]["startMs"] = cursor_ms
            for word in boundaries:
                start = cursor_ms + int(word["startMs"]) - first_ms
                end = cursor_ms + int(word["endMs"]) - first_ms
                words.append({"text": word["text"], "startMs": start, "endMs": end})
                captions.append({"text": " " + str(word["text"]), "startMs": start, "endMs": end, "timestampMs": None, "confidence": None})
            cursor_ms += last_ms - first_ms + 105 + gap_ms
            ranges[chapter_index]["endMs"] = cursor_ms
        chapter_filters.append(
            "".join(f"[s{i}]" for i in range(len(chapter_items)))
            + f"concat=n={len(chapter_items)}:v=0:a=1[out]"
        )
        chapter_path = PUBLIC / f"_chapter_{chapter_index:02d}.wav"
        chapter_command.extend([
            "-filter_complex", ";".join(chapter_filters), "-map", "[out]",
            "-c:a", "pcm_s16le", str(chapter_path),
        ])
        subprocess.run(chapter_command, check=True, capture_output=True)
        chapter_audio.append(chapter_path)

    narration = PUBLIC / "narration.mp3"
    final_command = ["ffmpeg", "-y"]
    for path in chapter_audio:
        final_command.extend(["-i", str(path)])
    final_filter = "".join(f"[{i}:a]" for i in range(len(chapter_audio))) + f"concat=n={len(chapter_audio)}:v=0:a=1[out]"
    final_command.extend(["-filter_complex", final_filter, "-map", "[out]", "-c:a", "libmp3lame", "-b:a", "192k", str(narration)])
    subprocess.run(final_command, check=True, capture_output=True)
    for path in chapter_audio:
        path.unlink(missing_ok=True)

    duration_ms = round(MP3(narration).info.length * 1000)
    payload = {"durationMs": duration_ms, "chapters": ranges, "words": words}
    (PUBLIC / "data.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (PUBLIC / "captions.json").write_text(json.dumps(captions, ensure_ascii=False, indent=2), encoding="utf-8")
    script = "\n\n".join(f"{chapter['title']}\n" + " ".join(chapter["sentences"]) for chapter in CHAPTERS)
    (OUTPUT / "narration_script.txt").write_text(script, encoding="utf-8")
    shutil.copy2(narration, OUTPUT / "narration_emel.mp3")
    print(json.dumps({"durationMs": duration_ms, "minutes": round(duration_ms / 60000, 2), "chapters": len(CHAPTERS), "words": len(words)}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
