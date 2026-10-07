//+------------------------------------------------------------------+
//|                                            XAU_Sniper_Razgon.mq5 |
//|  Oltin (XAUUSD / XAUUSDc) uchun ko'p timeframe'li "sniper" razgon |
//|                                                                  |
//|  D1  : kunlik yopilish EMA50 ning trend tomonida                 |
//|  H4  : EMA50 > EMA200 -> faqat BUY, EMA50 < EMA200 -> faqat SELL |
//|  H1  : narx trend bo'yicha EMA20 zonasiga qaytgan, EMA50 buzilmagan|
//|  M15 : oxirgi yopilgan sham oldingi shamlar cho'qqisini (tubini)  |
//|        yorsa - kirish. SL oxirgi M15 tublik (cho'qqi) ortida      |
//|  TP  : SL masofasi x RR (standart 1:3)                           |
//|  Lot : SL urilsa balansning InpRiskPercent foizi yo'qotiladi      |
//|  Maqsad: balans boshlang'ichdan InpGoalX baravar bo'lsa - hamma  |
//|        pozitsiya yopiladi va EA to'xtaydi                        |
//+------------------------------------------------------------------+
#property copyright "YunusjonAI"
#property version   "1.00"
#property description "D1/H4 trend + H1 qaytish zonasi + M15 sniper kirish. Risk % bo'yicha lot, TP = RR x SL."
#property description "Balans maqsadi (standart 4x) bajarilsa hamma pozitsiya yopiladi va EA to'xtaydi."

#include <Trade\Trade.mqh>

input group "Razgon"
input double InpRiskPercent  = 33.0;   // Har savdoda risk, balansdan % (SL urilsa shuncha yo'qotiladi)
input double InpRR           = 3.0;    // TP = SL masofasi x RR
input double InpGoalX        = 4.0;    // Balans maqsadi, necha baravar (yetganda hammasi yopiladi, EA to'xtaydi; 0 = o'chiq)
input double InpStartBalance = 0.0;    // Boshlang'ich balans (0 = EA birinchi ishga tushgandagi balans)
input bool   InpResetGoal    = false;  // true: boshlang'ich balans va "maqsad bajarildi" holatini yangilash
input double InpBreakevenR   = 0.0;    // Foyda shuncha R bo'lsa SL zararsiz nuqtaga (0 = o'chiq)
input int    InpMaxTradesDay = 3;      // Kuniga ko'pi bilan nechta savdo

input group "Sniper: timeframe'lar"
input bool   InpUseD1        = true;   // D1: kunlik yopilish EMA50 ning trend tomonida bo'lsin
input int    InpTrendFast    = 50;     // H4 tez EMA
input int    InpTrendSlow    = 200;    // H4 sekin EMA
input int    InpZoneFast     = 20;     // H1 qaytish zonasi EMA
input int    InpZoneSlow     = 50;     // H1 tuzilma EMA (narx uning trend tomonida bo'lsin)
input int    InpZoneBars     = 6;      // H1: oxirgi necha shamda zonaga tegilgan bo'lsin
input int    InpTriggerBars  = 4;      // M15: oldingi necha sham cho'qqisi (tubi) yorilsa - kirish
input int    InpSwingBars    = 8;      // M15: SL qo'yiladigan tublik (cho'qqi) uchun necha sham
input double InpMinStopATR   = 0.5;    // SL masofasi kamida shuncha x ATR(M15)
input double InpMaxStopATR   = 3.0;    // SL masofasi ko'pi bilan shuncha x ATR(M15)

input group "Filtrlar"
input int    InpStartHour    = 7;      // Savdo boshlanishi, server vaqti (Exness: GMT)
input int    InpEndHour      = 20;     // Savdo tugashi, server vaqti
input double InpMaxSpreadUSD = 1.00;   // Spred shundan katta bo'lsa kirilmaydi (narxda, $)
input double InpMaxSpreadSL  = 10.0;   // Spred SL masofasining necha foizidan oshsa kirilmaydi
input bool   InpNewsFilter   = true;   // Muhim USD yangiliklari atrofida kirilmaydi (testerda ishlamaydi)
input int    InpNewsMinutes  = 30;     // Yangilikdan oldin va keyin necha daqiqa
input bool   InpFridayClose  = true;   // Juma kuni pozitsiyalarni yopish (dam olish kunlari gap xavfi)
input int    InpFridayHour   = 20;     // Juma, server vaqti: shu soatda yopiladi (4 soat oldin yangi kirish yo'q)

input group "Boshqa"
input long   InpMagic        = 770077; // EA savdolari belgisi (magic number)
input double InpSlippageUSD  = 0.50;   // Ruxsat etilgan sirpanish ($)
input bool   InpPush         = true;   // Telefonga push xabar (MT5 sozlamalarida MetaQuotes ID kerak)

CTrade   trade;
int      hD1  = INVALID_HANDLE;
int      hH4f = INVALID_HANDLE;
int      hH4s = INVALID_HANDLE;
int      hH1f = INVALID_HANDLE;
int      hH1s = INVALID_HANDLE;
int      hATR = INVALID_HANDLE;
double   g_start   = 0.0;
bool     g_done    = false;
datetime g_lastBar = 0;
int      g_today   = 0;
string   g_state   = "ishga tushdi";
bool     g_tester  = false;
datetime g_since   = 0;     // statistika shu vaqtdan hisoblanadi
int      g_wins    = 0;
int      g_losses  = 0;
double   g_net     = 0.0;
string   GV_START;
string   GV_DONE;
string   GV_SINCE;

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpRiskPercent <= 0 || InpRiskPercent > 100 || InpRR <= 0 || InpZoneBars < 1 ||
      InpTriggerBars < 1 || InpSwingBars < 1 || InpMaxSpreadSL <= 0)
     {
      Print("Sozlamalar xato: InpRiskPercent 0..100, InpRR > 0, InpMaxSpreadSL > 0, shamlar soni kamida 1 bo'lishi kerak");
      return INIT_PARAMETERS_INCORRECT;
     }
   hD1  = iMA(_Symbol, PERIOD_D1, 50, 0, MODE_EMA, PRICE_CLOSE);
   hH4f = iMA(_Symbol, PERIOD_H4, InpTrendFast, 0, MODE_EMA, PRICE_CLOSE);
   hH4s = iMA(_Symbol, PERIOD_H4, InpTrendSlow, 0, MODE_EMA, PRICE_CLOSE);
   hH1f = iMA(_Symbol, PERIOD_H1, InpZoneFast, 0, MODE_EMA, PRICE_CLOSE);
   hH1s = iMA(_Symbol, PERIOD_H1, InpZoneSlow, 0, MODE_EMA, PRICE_CLOSE);
   hATR = iATR(_Symbol, PERIOD_M15, 14);
   if(hD1 == INVALID_HANDLE || hH4f == INVALID_HANDLE || hH4s == INVALID_HANDLE ||
      hH1f == INVALID_HANDLE || hH1s == INVALID_HANDLE || hATR == INVALID_HANDLE)
     {
      Print("Indikatorlarni yaratib bo'lmadi");
      return INIT_FAILED;
     }

   trade.SetExpertMagicNumber((ulong)InpMagic);
   trade.SetDeviationInPoints((ulong)MathMax(1.0, InpSlippageUSD / _Point));
   trade.SetTypeFillingBySymbol(_Symbol);

   // Boshlang'ich balans va "maqsad bajarildi" terminal qayta ochilsa ham saqlanadi (testerda emas)
   g_tester = MQLInfoInteger(MQL_TESTER) != 0;
   GV_START = "XSR_" + _Symbol + "_" + IntegerToString(InpMagic) + "_start";
   GV_DONE  = "XSR_" + _Symbol + "_" + IntegerToString(InpMagic) + "_done";
   GV_SINCE = "XSR_" + _Symbol + "_" + IntegerToString(InpMagic) + "_since";
   if(InpResetGoal && !g_tester)
     {
      GlobalVariableDel(GV_START);
      GlobalVariableDel(GV_DONE);
      GlobalVariableDel(GV_SINCE);
     }
   if(InpStartBalance > 0)
      g_start = InpStartBalance;
   else
      if(!g_tester && GlobalVariableCheck(GV_START))
         g_start = GlobalVariableGet(GV_START);
      else
         g_start = AccountInfoDouble(ACCOUNT_BALANCE);
   if(!g_tester && GlobalVariableCheck(GV_SINCE))
      g_since = (datetime)GlobalVariableGet(GV_SINCE);
   else
      g_since = TimeCurrent();
   if(!g_tester)
     {
      GlobalVariableSet(GV_START, g_start);
      GlobalVariableSet(GV_SINCE, (double)g_since);
     }
   g_done = !g_tester && GlobalVariableCheck(GV_DONE) && GlobalVariableGet(GV_DONE) > 0;
   UpdateStats();

   PrintFormat("XAU Sniper Razgon: boshlanish %.2f, maqsad %.2fx = %.2f, risk %.1f%%, RR 1:%.1f",
               g_start, InpGoalX, g_start * InpGoalX, InpRiskPercent, InpRR);
   ShowPanel(g_done ? "MAQSAD BAJARILGAN - EA to'xtagan" : g_state);
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   IndicatorRelease(hD1);
   IndicatorRelease(hH4f);
   IndicatorRelease(hH4s);
   IndicatorRelease(hH1f);
   IndicatorRelease(hH1s);
   IndicatorRelease(hATR);
   Comment("");
  }

//+------------------------------------------------------------------+
//| Indikator qiymati (shift = 1 -> oxirgi yopilgan sham)             |
//+------------------------------------------------------------------+
double Buf(const int handle, const int shift)
  {
   double v[];
   if(CopyBuffer(handle, 0, shift, 1, v) != 1)
      return EMPTY_VALUE;
   return v[0];
  }

//+------------------------------------------------------------------+
//| PositionGetTicket() tanlagan pozitsiya shu EA nikimi              |
//+------------------------------------------------------------------+
bool IsOwn()
  {
   return PositionGetString(POSITION_SYMBOL) == _Symbol && PositionGetInteger(POSITION_MAGIC) == InpMagic;
  }

int OwnPositions()
  {
   int n = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
      if(PositionGetTicket(i) > 0 && IsOwn())
         n++;
   return n;
  }

void CloseAll(const string why)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !IsOwn())
         continue;
      if(!trade.PositionClose(ticket))
         PrintFormat("Yopib bo'lmadi #%I64u: %u %s", ticket, trade.ResultRetcode(), trade.ResultRetcodeDescription());
     }
   PrintFormat("Hamma pozitsiya yopildi: %s", why);
  }

//+------------------------------------------------------------------+
//| Bugun shu EA ochgan savdolar soni                                 |
//+------------------------------------------------------------------+
int TradesToday()
  {
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   dt.hour = 0;
   dt.min  = 0;
   dt.sec  = 0;
   if(!HistorySelect(StructToTime(dt), TimeCurrent() + 60))
      return 0;
   int n = 0;
   for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
     {
      ulong deal = HistoryDealGetTicket(i);
      if(deal == 0)
         continue;
      if(HistoryDealGetString(deal, DEAL_SYMBOL) == _Symbol &&
         HistoryDealGetInteger(deal, DEAL_MAGIC) == InpMagic &&
         (ENUM_DEAL_ENTRY)HistoryDealGetInteger(deal, DEAL_ENTRY) == DEAL_ENTRY_IN)
         n++;
     }
   return n;
  }

//+------------------------------------------------------------------+
//| Muhim (HIGH) USD yangiligi +-InpNewsMinutes ichidami               |
//+------------------------------------------------------------------+
bool NewsBlocked()
  {
   if(!InpNewsFilter || MQLInfoInteger(MQL_TESTER))
      return false;
   datetime now = TimeTradeServer();
   MqlCalendarValue values[];
   if(!CalendarValueHistory(values, now - InpNewsMinutes * 60, now + InpNewsMinutes * 60, NULL, "USD"))
      return false;
   int n = ArraySize(values);
   for(int i = 0; i < n; i++)
     {
      MqlCalendarEvent ev;
      if(CalendarEventById(values[i].event_id, ev) && ev.importance == CALENDAR_IMPORTANCE_HIGH)
        {
         g_state = "muhim yangilik yaqin: " + ev.name;
         return true;
        }
     }
   return false;
  }

//+------------------------------------------------------------------+
//| Risk bo'yicha lot: SL urilsa balansning InpRiskPercent foizi      |
//+------------------------------------------------------------------+
double LotsForRisk(const double stop_dist, const ENUM_ORDER_TYPE type, const double price)
  {
   double risk_money = AccountInfoDouble(ACCOUNT_BALANCE) * InpRiskPercent / 100.0;
   double tick_size  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double tick_value = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE_LOSS);
   if(tick_value <= 0)
      tick_value = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double vmax = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(tick_size <= 0 || tick_value <= 0 || step <= 0 || stop_dist <= 0)
      return 0.0;

   double loss_per_lot = stop_dist / tick_size * tick_value;
   double lots = MathFloor(risk_money / loss_per_lot / step) * step;
   if(lots < vmin)
     {
      if(vmin * loss_per_lot > risk_money * 1.5)
        {
         g_state = StringFormat("minimal lot (%.2f) riski %.2f > ruxsat %.2f - o'tkazildi",
                                vmin, vmin * loss_per_lot, risk_money);
         return 0.0;
        }
      lots = vmin;
     }
   lots = MathMin(lots, vmax);

   double margin = 0.0;
   double free_margin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   if(OrderCalcMargin(type, _Symbol, lots, price, margin) && margin > free_margin * 0.9)
     {
      lots = MathFloor(lots * free_margin * 0.9 / margin / step) * step;
      if(lots < vmin)
        {
         g_state = "marja yetmaydi - o'tkazildi";
         return 0.0;
        }
     }
   return NormalizeDouble(lots, 2);
  }

//+------------------------------------------------------------------+
//| Sniper signal: 1 = BUY, -1 = SELL, 0 = yo'q                       |
//+------------------------------------------------------------------+
int Signal(double &sl, double &tp, double &entry)
  {
   double atr = Buf(hATR, 1);
   double h4f = Buf(hH4f, 1);
   double h4s = Buf(hH4s, 1);
   double h1s = Buf(hH1s, 1);
   if(atr == EMPTY_VALUE || h4f == EMPTY_VALUE || h4s == EMPTY_VALUE || h1s == EMPTY_VALUE || atr <= 0)
     {
      g_state = "tarix yuklanmoqda";
      return 0;
     }

   // H4: yo'nalish
   int dir = 0;
   if(h4f > h4s)
      dir = 1;
   if(h4f < h4s)
      dir = -1;
   if(dir == 0)
     {
      g_state = "H4: trend yo'q";
      return 0;
     }

   // D1: kunlik yopilish trend tomonida
   if(InpUseD1)
     {
      double d1 = Buf(hD1, 1);
      double d1close = iClose(_Symbol, PERIOD_D1, 1);
      if(d1 == EMPTY_VALUE || d1close <= 0)
         return 0;
      if((dir > 0 && d1close < d1) || (dir < 0 && d1close > d1))
        {
         g_state = "D1 H4 trendiga qarshi";
         return 0;
        }
     }

   // H1: tuzilma buzilmagan va narx EMA zonasiga qaytgan
   double h1close = iClose(_Symbol, PERIOD_H1, 1);
   if(h1close <= 0 || (dir > 0 && h1close < h1s) || (dir < 0 && h1close > h1s))
     {
      g_state = "H1 tuzilma buzilgan";
      return 0;
     }
   double zf[], hl[];
   ArraySetAsSeries(zf, true);
   ArraySetAsSeries(hl, true);
   if(CopyBuffer(hH1f, 0, 1, InpZoneBars, zf) != InpZoneBars)
      return 0;
   int got = (dir > 0) ? CopyLow(_Symbol, PERIOD_H1, 1, InpZoneBars, hl)
                       : CopyHigh(_Symbol, PERIOD_H1, 1, InpZoneBars, hl);
   if(got != InpZoneBars)
      return 0;
   bool touched = false;
   for(int i = 0; i < InpZoneBars; i++)
      if((dir > 0 && hl[i] <= zf[i]) || (dir < 0 && hl[i] >= zf[i]))
        {
         touched = true;
         break;
        }
   if(!touched)
     {
      g_state = "H1: zonaga qaytish kutilmoqda";
      return 0;
     }

   // M15: sniper kirish - oxirgi yopilgan sham oldingi shamlar cho'qqisini (tubini) yordi
   double c1 = iClose(_Symbol, PERIOD_M15, 1);
   int idx = (dir > 0) ? iHighest(_Symbol, PERIOD_M15, MODE_HIGH, InpTriggerBars, 2)
                       : iLowest(_Symbol, PERIOD_M15, MODE_LOW, InpTriggerBars, 2);
   if(idx < 0 || c1 <= 0)
      return 0;
   double level = (dir > 0) ? iHigh(_Symbol, PERIOD_M15, idx) : iLow(_Symbol, PERIOD_M15, idx);
   if((dir > 0 && c1 <= level) || (dir < 0 && c1 >= level))
     {
      g_state = "M15: sniper kirish kutilmoqda";
      return 0;
     }

   // SL: oxirgi M15 tublik (cho'qqi) ortida + zaxira
   int sidx = (dir > 0) ? iLowest(_Symbol, PERIOD_M15, MODE_LOW, InpSwingBars, 1)
                        : iHighest(_Symbol, PERIOD_M15, MODE_HIGH, InpSwingBars, 1);
   if(sidx < 0)
      return 0;
   double swing  = (dir > 0) ? iLow(_Symbol, PERIOD_M15, sidx) : iHigh(_Symbol, PERIOD_M15, sidx);
   double ask    = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid    = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double spread = ask - bid;
   double buffer = MathMax(spread * 2.0, atr * 0.1);
   entry = (dir > 0) ? ask : bid;
   sl    = (dir > 0) ? swing - buffer : swing + buffer;
   if((dir > 0 && sl >= entry) || (dir < 0 && sl <= entry))
     {
      g_state = "SL noto'g'ri tomonda - o'tkazildi";
      return 0;
     }
   double dist = MathAbs(entry - sl);
   double min_stop = MathMax(InpMinStopATR * atr,
                             (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point + spread);
   if(dist < min_stop || dist > InpMaxStopATR * atr)
     {
      g_state = StringFormat("SL masofasi mos emas (%.2f, ATR %.2f)", dist, atr);
      return 0;
     }
   if(spread > dist * InpMaxSpreadSL / 100.0)
     {
      g_state = StringFormat("spred SL ga nisbatan katta (%.2f / %.2f)", spread, dist);
      return 0;
     }
   tp    = (dir > 0) ? entry + InpRR * dist : entry - InpRR * dist;
   sl    = NormalizeDouble(sl, _Digits);
   tp    = NormalizeDouble(tp, _Digits);
   entry = NormalizeDouble(entry, _Digits);
   return dir;
  }

//+------------------------------------------------------------------+
//| Foyda InpBreakevenR R ga yetsa SL zararsiz nuqtaga                |
//+------------------------------------------------------------------+
void ManageBreakeven()
  {
   if(InpBreakevenR <= 0)
      return;
   double spread = SymbolInfoDouble(_Symbol, SYMBOL_ASK) - SymbolInfoDouble(_Symbol, SYMBOL_BID);
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !IsOwn())
         continue;
      double open = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl   = PositionGetDouble(POSITION_SL);
      double tp   = PositionGetDouble(POSITION_TP);
      if(tp <= 0)
         continue;
      double risk = MathAbs(tp - open) / InpRR;
      bool is_long = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY;
      double price = is_long ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double be = NormalizeDouble(is_long ? open + spread : open - spread, _Digits);
      if(is_long && price - open >= InpBreakevenR * risk && sl < be)
         trade.PositionModify(ticket, be, tp);
      if(!is_long && open - price >= InpBreakevenR * risk && (sl > be || sl == 0))
         trade.PositionModify(ticket, be, tp);
     }
  }

//+------------------------------------------------------------------+
void ShowPanel(const string state)
  {
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   Comment(StringFormat("XAU Sniper Razgon  |  %s\n"
                        "Boshlanish: %.2f   Hozir: %.2f  (%.2fx)\n"
                        "Maqsad: %.1fx = %.2f   |   risk %.0f%%   RR 1:%.1f\n"
                        "Bugungi savdolar: %d / %d\n"
                        "Natija: %d savdo (foyda %d, zarar %d), jami %+.2f\n"
                        "Holat: %s",
                        _Symbol, g_start, eq, g_start > 0 ? eq / g_start : 0.0,
                        InpGoalX, g_start * InpGoalX, InpRiskPercent, InpRR,
                        g_today, InpMaxTradesDay, g_wins + g_losses, g_wins, g_losses, g_net, state));
  }

//+------------------------------------------------------------------+
void OnTick()
  {
   if(g_done)
     {
      if(OwnPositions() > 0)   // yopilmay qolgan bo'lsa, qayta urinish
         CloseAll("maqsad bajarilgan");
      ShowPanel("MAQSAD BAJARILGAN - EA to'xtagan (qayta boshlash: InpResetGoal = true)");
      return;
     }

   // Balans maqsadi: hammasini yopib, to'xtash
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   if(InpGoalX > 0 && g_start > 0 && equity >= g_start * InpGoalX)
     {
      CloseAll("maqsad bajarildi");
      g_done = true;
      if(!g_tester)
         GlobalVariableSet(GV_DONE, 1.0);
      string msg = StringFormat("XAU Sniper Razgon: MAQSAD BAJARILDI! Balans %.2f (%.2fx)", equity, equity / g_start);
      Alert(msg);
      Notify(msg);
      ShowPanel("MAQSAD BAJARILDI");
      return;
     }

   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   if(InpFridayClose && dt.day_of_week == 5 && dt.hour >= InpFridayHour)
     {
      if(OwnPositions() > 0)
         CloseAll("juma - dam olish kunlaridan oldin");
      ShowPanel("juma: savdo yopiq");
      return;
     }

   ManageBreakeven();

   // Har yangi M15 shamda bir marta tekshiramiz
   datetime bar = iTime(_Symbol, PERIOD_M15, 0);
   if(bar == g_lastBar)
     {
      ShowPanel(g_state);
      return;
     }
   g_lastBar = bar;
   g_today = TradesToday();

   if(OwnPositions() > 0)
      g_state = "pozitsiya ochiq";
   else
      if(g_today >= InpMaxTradesDay)
         g_state = "bugungi savdolar limiti";
      else
         if(dt.day_of_week == 0 || dt.day_of_week == 6)
            g_state = "dam olish kuni";
         else
            if(dt.hour < InpStartHour || dt.hour >= InpEndHour)
               g_state = "sessiya tashqarisida";
            else
               if(InpFridayClose && dt.day_of_week == 5 && dt.hour >= InpFridayHour - 4)
                  g_state = "juma: yangi kirish yo'q";
               else
                 {
                  double spread = SymbolInfoDouble(_Symbol, SYMBOL_ASK) - SymbolInfoDouble(_Symbol, SYMBOL_BID);
                  if(spread > InpMaxSpreadUSD)
                     g_state = StringFormat("spred katta (%.2f)", spread);
                  else
                     if(!NewsBlocked())
                        TryEnter();
                 }
   ShowPanel(g_state);
  }

//+------------------------------------------------------------------+
void TryEnter()
  {
   double sl = 0, tp = 0, entry = 0;
   int dir = Signal(sl, tp, entry);
   if(dir == 0)
      return;
   ENUM_ORDER_TYPE type = (dir > 0) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   double lots = LotsForRisk(MathAbs(entry - sl), type, entry);
   if(lots <= 0)
      return;
   bool ok = (dir > 0) ? trade.Buy(lots, _Symbol, entry, sl, tp, "XSR razgon")
                       : trade.Sell(lots, _Symbol, entry, sl, tp, "XSR razgon");
   uint rc = trade.ResultRetcode();
   if(ok && (rc == TRADE_RETCODE_DONE || rc == TRADE_RETCODE_PLACED))
     {
      g_today++;
      g_state = StringFormat("%s %.2f lot @ %.2f | SL %.2f | TP %.2f", dir > 0 ? "BUY" : "SELL", lots, entry, sl, tp);
      Notify("XSR " + _Symbol + " " + g_state);
     }
   else
     {
      g_state = StringFormat("order xatosi: %u %s", rc, trade.ResultRetcodeDescription());
      Print(g_state);
     }
  }

//+------------------------------------------------------------------+
//| Terminal jurnaliga yozish + telefonga push                        |
//+------------------------------------------------------------------+
void Notify(const string msg)
  {
   Print(msg);
   if(!InpPush || g_tester)
      return;
   static bool warned = false;
   if(!SendNotification(msg) && !warned)
     {
      warned = true;
      Print("Push yuborilmadi: MT5 -> Tools -> Options -> Notifications da MetaQuotes ID ni kiriting");
     }
  }

//+------------------------------------------------------------------+
//| g_since dan beri shu EA yopgan savdolar: foyda/zarar soni, jami   |
//+------------------------------------------------------------------+
void UpdateStats()
  {
   g_wins   = 0;
   g_losses = 0;
   g_net    = 0.0;
   if(!HistorySelect(g_since, TimeCurrent() + 60))
      return;
   int total = HistoryDealsTotal();
   long own[];
   int n_own = 0;
   for(int i = 0; i < total; i++)
     {
      ulong deal = HistoryDealGetTicket(i);
      if(deal == 0)
         continue;
      if(HistoryDealGetString(deal, DEAL_SYMBOL) == _Symbol &&
         HistoryDealGetInteger(deal, DEAL_MAGIC) == InpMagic &&
         (ENUM_DEAL_ENTRY)HistoryDealGetInteger(deal, DEAL_ENTRY) == DEAL_ENTRY_IN)
        {
         ArrayResize(own, n_own + 1);
         own[n_own] = HistoryDealGetInteger(deal, DEAL_POSITION_ID);
         n_own++;
         g_net += HistoryDealGetDouble(deal, DEAL_COMMISSION);
        }
     }
   for(int i = 0; i < total; i++)
     {
      ulong deal = HistoryDealGetTicket(i);
      if(deal == 0)
         continue;
      ENUM_DEAL_ENTRY entry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(deal, DEAL_ENTRY);
      if(entry != DEAL_ENTRY_OUT && entry != DEAL_ENTRY_OUT_BY)
         continue;
      long pos = HistoryDealGetInteger(deal, DEAL_POSITION_ID);
      bool mine = false;
      for(int j = 0; j < n_own && !mine; j++)
         mine = (own[j] == pos);
      if(!mine)
         continue;
      double pnl = HistoryDealGetDouble(deal, DEAL_PROFIT) + HistoryDealGetDouble(deal, DEAL_SWAP) +
                   HistoryDealGetDouble(deal, DEAL_COMMISSION);
      g_net += pnl;
      if(pnl > 0)
         g_wins++;
      else
         g_losses++;
     }
  }

//+------------------------------------------------------------------+
//| Savdo yopilganda: statistika va telefonga xabar                   |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
  {
   if(trans.type != TRADE_TRANSACTION_DEAL_ADD || trans.symbol != _Symbol)
      return;
   if(!HistoryDealSelect(trans.deal))
      return;
   ENUM_DEAL_ENTRY entry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(trans.deal, DEAL_ENTRY);
   if(entry != DEAL_ENTRY_OUT && entry != DEAL_ENTRY_OUT_BY)
      return;
   double pnl = HistoryDealGetDouble(trans.deal, DEAL_PROFIT) + HistoryDealGetDouble(trans.deal, DEAL_SWAP) +
                HistoryDealGetDouble(trans.deal, DEAL_COMMISSION);
   ENUM_DEAL_REASON why = (ENUM_DEAL_REASON)HistoryDealGetInteger(trans.deal, DEAL_REASON);
   int before = g_wins + g_losses;
   UpdateStats();
   if(g_wins + g_losses == before)
      return;   // bu EA ning pozitsiyasi emas
   string tag = "yopildi";
   if(why == DEAL_REASON_TP)
      tag = "TP";
   if(why == DEAL_REASON_SL)
      tag = "SL";
   double bal = AccountInfoDouble(ACCOUNT_BALANCE);
   Notify(StringFormat("XSR %s %s: %+.2f | balans %.2f (%.2fx)", _Symbol, tag, pnl, bal,
                       g_start > 0 ? bal / g_start : 0.0));
  }
//+------------------------------------------------------------------+
