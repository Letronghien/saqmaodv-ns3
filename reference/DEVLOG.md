# DEVLOG — QSAQMAODV-NS3 Experiment Pipeline

> Ghi chép toàn bộ quá trình xây dựng, debug và chạy thí nghiệm cho bài báo Q3.
> Cập nhật lần cuối: 2026-06-06

---

## 0. Cấu trúc dự án

### 0.1 Repo GitHub (`Letronghien/qsaqmaodv-ns3`)

```
qsaqmaodv-ns3/
├── README.md                        # Tổng quan + quick start
├── PAPER-OUTLINE.md                 # Outline bài báo
├── DEVLOG.md                        # File này
├── bootstrap-hsaqmaodv.py           # Bootstrap script (legacy)
├── files.tar                        # Archive các file custom
│
├── files/                           # Custom .h/.cc cho các NS-3 module
│   ├── aomdv-multipath-table.{h,cc} # AOMDV multipath routing table
│   ├── pmaodv-multipath-table.{h,cc}# PMAODV multipath routing table
│   ├── qmaodv-qtable.{h,cc}         # QMAODV Q-learning table
│   └── saqmaodv-qtable.{h,cc}       # SA-QMAODV adaptive Q-table
│                                    # (QSAQMAODV table nằm trong ns-3 src)
│
├── src/
│   ├── fanet-sim.cc                 # ⭐ Main simulation driver
│   │                                #    CLI flags: --protocol --numNodes
│   │                                #    --qs* --qm* --sa* --simTime ...
│   └── fix-fanet-sim.py             # Utility: hoàn thiện file bị truncate
│
├── scripts/
│   ├── setup/
│   │   └── setup-from-scratch.sh   # ⭐ Cài đặt đầy đủ: clone modules,
│   │                                #    apply patches, build ns-3
│   ├── run/
│   │   ├── run-paper-full.sh       # ⭐ Chạy toàn bộ 8 họ (v3)
│   │   ├── run-paper-experiments.sh# Script gốc 5-family (SAQMAODV)
│   │   ├── run-family-N.sh         # Script riêng Family N
│   │   ├── run-hetero-battery.sh   # Heterogeneous battery scenario
│   │   ├── run-long-sim.sh         # Long sim convergence
│   │   └── run-paper-exact.sh      # Paper §5 exact reproduction
│   ├── plot/
│   │   ├── plot-family-N.py        # ⭐ Plot Family N (QSAQMAODV)
│   │   ├── plot-experiments-5proto.py # Plot 5 protocols (cần update)
│   │   └── aggregate-for-paper.py  # Tổng hợp CSV cho paper
│   └── patches/                    # 22 Python patch scripts
│       ├── apply-phase-2.3*.py     # PMAODV patches
│       ├── apply-aomdv-*.py        # AOMDV patches
│       ├── apply-qmaodv-*.py       # QMAODV patches
│       └── apply-saqmaodv-*.py     # SA-QMAODV patches
│
├── notes/                           # Ghi chú nghiên cứu
├── reference/
│   ├── QMAODV-Paper-v3.docx        # Paper QMAODV (tiếng Việt)
│   └── SA-QMAODV-Final.pdf         # Paper SA-QMAODV gốc
└── results/                         # Kết quả thí nghiệm (gitignored)
```

> **Lưu ý quan trọng:** `src/fanet-sim.cc` trong repo từng bị truncate ở dòng ~420
> (thiếu phần OnOff app + FlowMonitor + CSV). Đã fix bằng `fix-fanet-sim.py`.
> Luôn kiểm tra: `wc -l src/fanet-sim.cc` → phải ≥ 550 dòng.

---

### 0.2 Cấu trúc VM (Google Cloud)

```
~/ (home của tronghien1011)
│
├── qsaqmaodv-ns3/                   # ⭐ Repo chính (git clone)
│   └── (cấu trúc như trên)
│
├── ns-allinone-3.40-qsaqmaodv/      # ⭐ NS-3 installation cho dự án này
│   └── ns-3.40/
│       ├── src/
│       │   ├── aodv/                # Stock AODV (giữ nguyên)
│       │   ├── pmaodv/              # Clone từ aodv + patches PMAODV
│       │   ├── aomdv/               # Clone từ aodv + patches AOMDV
│       │   ├── qmaodv/              # Clone từ aodv + patches QMAODV
│       │   ├── saqmaodv/            # Clone từ aodv + patches SA-QMAODV
│       │   └── qsaqmaodv/           # ⭐ Module mới — QS-QMAODV
│       │       ├── model/
│       │       │   ├── qsaqmaodv-routing-protocol.{h,cc}
│       │       │   ├── qsaqmaodv-rtable.{h,cc}
│       │       │   └── qsaqmaodv-qtable.{h,cc}  # Queue-State Q-table
│       │       └── CMakeLists.txt
│       ├── scratch/
│       │   └── fanet-sim.cc         # ⭐ Copy từ repo/src/, đây là file compile
│       └── build/scratch/
│           └── ns3.40-fanet-sim-optimized  # ⭐ Binary thực thi
│
├── results-paper-full-<timestamp>/  # Kết quả chạy (tạo tự động)
│   ├── run_full.log
│   ├── done.txt
│   ├── family_N_nodes.csv
│   └── ...
│
│   # Các NS-3 installations cũ (tham khảo khi cần):
├── ns-allinone-3.40-hsaqmaodv/      # NS-3 cho dự án HSAQMAODV
├── ns-allinone-3.40/                # NS-3 stock (không custom)
├── ns-allinone-3.42/                # NS-3.42 (phiên bản mới hơn)
│
│   # Các repo cũ (nguồn tham khảo code):
├── hsaqmaodv-ns3/                   # ⭐ Repo HSAQMAODV — fanet-sim.cc đầy đủ 498 dòng
│   └── src/fanet-sim.cc             #    Dùng làm reference khi fix truncated file
├── saqmaodv-deploy-20260521-032404/ # Deploy script SA-QMAODV cũ
├── qmaodv-ns3/                      # Repo QMAODV
├── fanet-multipath-ns3/             # Repo multipath cũ
├── pmaodv-fanet-cloud/              # Repo PMAODV
└── stress-update/                   # Update files
```

### 0.3 Quy trình thiết lập lần đầu (Fresh Setup)

```bash
# 1. Clone repo
git clone https://github.com/Letronghien/qsaqmaodv-ns3.git
cd qsaqmaodv-ns3

# 2. Cài đặt NS-3 modules + build (~10 phút)
bash scripts/setup/setup-from-scratch.sh

# 3. Verify 5 protocols hoạt động
EXEC=~/ns-allinone-3.40-qsaqmaodv/ns-3.40/build/scratch/ns3.40-fanet-sim-optimized
for P in AODV AOMDV PMAODV QMAODV QSAQMAODV; do
    $EXEC --protocol=$P --numNodes=5 --simTime=10 --maxPaths=3 \
          --seed=1 --csvFile=/tmp/test.csv 2>&1 | grep "delivery="
    echo "→ $P: rc=$?"
done

# 4. Verify --qs* flags (QSAQMAODV đặc biệt)
$EXEC --protocol=QSAQMAODV --numNodes=5 --simTime=10 --maxPaths=3 \
      --qsAlpha0=0.5 --qsW3=0.10 --seed=1 --csvFile=/tmp/test.csv 2>&1 | tail -2
echo "rc=$?"   # phải là 0 hoặc 139
```

> **Quan hệ giữa repo và NS-3:**
> - `setup-from-scratch.sh` tạo các module (`src/pmaodv`, `src/aomdv`...) bằng cách clone từ `src/aodv` rồi apply patches
> - `src/fanet-sim.cc` (repo) được copy sang `scratch/fanet-sim.cc` (ns-3) rồi compile
> - Các file trong `files/` được copy vào đúng module tương ứng trong ns-3

---

## 1. Tổng quan dự án

**Mục tiêu:** Đánh giá toàn diện QS-QMAODV (Queue-State Self-Adaptive Q-learning Multipath AODV) so với 4 baseline trong môi trường FANET (NS-3.40).

**5 protocols:**

| Tên | Loại |
|-----|------|
| AODV | Baseline đơn đường |
| AOMDV-3 | Multipath baseline |
| PMAODV-3 | Probabilistic multipath |
| QMAODV-3 | Q-learning multipath |
| QSAQMAODV-3 | **Đề xuất mới** — Queue-State Self-Adaptive |

**Môi trường:**
- NS-3.40 tại `~/ns-allinone-3.40-qsaqmaodv/ns-3.40`
- Repo: `~/qsaqmaodv-ns3` (GitHub: `Letronghien/qsaqmaodv-ns3`)
- Binary: `build/scratch/ns3.40-fanet-sim-optimized`

---

## 2. Thiết kế thí nghiệm

### 6 họ kịch bản chính

| Họ | Biến sweep | Giá trị | Runs |
|----|-----------|---------|------|
| N | Số nodes | {5,10,15,20,25,30,40,50,75,100} × 5P × 30s | 1500 |
| S | Tốc độ max (m/s) | {5,10,20,30,50,70} × 5P × 30s | 900 |
| L | Packet interval (s) | {1.0,0.5,0.25,0.1,0.05} × 5P × 30s | 750 |
| E | Năng lượng E₀ (J) | {10,20,30,50,75,100} × 5P × 30s | 900 |
| W | Trọng số w₃ | {0.00–0.50, 7 bước} × QSAQMAODV × 30s | 210 |
| M | Load × Energy mixed | {0.5,0.25,0.05}s × {10,30,50}J × 5P × 30s | 1350 |

### 2 thí nghiệm bổ sung

| Tên | Mô tả | Runs |
|-----|-------|------|
| STAT | Baseline 50 seeds (statistical validation) | 250 |
| ELONG | E₀=10J, T=350s (energy depletion) | 150 |

**Tổng: ~6010 runs**

**Tham số baseline cố định:**
```
mobility=GAUSS, N=15, velMin=15, velMax=25 m/s
pktInterval=0.25s, pktSize=512B, simTime=200s, E₀=50J
```

**QSAQMAODV defaults:**
```
α₀=0.5, γ=0.9, ε₀=0.3, λ=0.1
w=(0.40, 0.30, 0.10, 0.20)  [w1,w2,w3,w4]
seqNoWin=5s, adaptPeriod=10s
lowEThresh=0.20, queueHigh=0.70, queueLow=0.30
```

**Family W:** w₁ = w₂ = (1 − w₃) / 2 khi sweep w₃.

---

## 3. Cấu trúc scripts

```
scripts/run/
├── run-paper-full.sh     # Script chính — toàn bộ 8 họ (v3, đã fix)
├── run-family-N.sh       # Script riêng Family N (legacy, 20 seeds)
└── run-paper-experiments.sh  # Script gốc 5-family (SAQMAODV)

scripts/plot/
├── plot-family-N.py      # Plot Family N với QSAQMAODV
└── plot-experiments-5proto.py  # Plot gốc (cần update protocol names)

src/
├── fix-fanet-sim.py      # Utility: hoàn thiện fanet-sim.cc bị truncate
└── fanet-sim.cc          # Main simulation driver
```

---

## 4. Hướng dẫn chạy thí nghiệm

### Lần đầu (fresh run)
```bash
cd ~/qsaqmaodv-ns3
git pull
ulimit -c 0                          # Tắt core dump
JOBS=3 bash scripts/run/run-paper-full.sh
```

### Resume sau khi bị ngắt
```bash
RDIR=$(ls -dt ~/results-paper-full-* | head -1)
ulimit -c 0
RESUME=1 JOBS=3 bash scripts/run/run-paper-full.sh
```
> Script tự đọc `$RDIR/done.txt` để bỏ qua các run đã xong.

### Chạy chọn lọc một số họ
```bash
FAMILIES="S L E" JOBS=3 bash scripts/run/run-paper-full.sh
```

### Kiểm tra tiến độ
```bash
RDIR=$(ls -dt ~/results-paper-full-* | head -1)
echo "OK:" && grep -c "^OK" $RDIR/run_full.log
echo "FAIL:" && grep -c "^FAIL" $RDIR/run_full.log
wc -l $RDIR/*.csv
```

### Plot kết quả
```bash
RDIR=$(ls -dt ~/results-paper-full-* | head -1)
mkdir -p ~/figures/{N,S,L,E,W,M}

python3 scripts/plot/plot-family-N.py $RDIR/family_N_nodes.csv ~/figures/N/
# (tương tự cho S, L, E, W, M)
```

---

## 5. Bugs đã gặp và cách fix

### Bug 1: Binary không nhận `--qs*` flags (rc=1)

**Triệu chứng:** QSAQMAODV fail 100% với rc=1, các protocol khác OK.

**Nguyên nhân:** Binary compile từ `fanet-sim.cc` cũ chưa có `CommandLine::AddValue` cho `--qsAlpha0`, `--qsW1`... Khi script truyền flag không tồn tại, ns-3 in help và exit rc=1.

**Cách phát hiện:**
```bash
$EXEC --protocol=QSAQMAODV --numNodes=5 --simTime=10 --qsAlpha0=0.5 \
      --seed=1 --csvFile=/tmp/t.csv 2>&1 | tail -3
# Output: "Invalid command-line argument: --q" → bug xác nhận
```

**Fix:** Copy `fanet-sim.cc` đầy đủ (có `--qs*` AddValue) vào scratch và rebuild:
```bash
cp ~/qsaqmaodv-ns3/src/fanet-sim.cc \
   ~/ns-allinone-3.40-qsaqmaodv/ns-3.40/scratch/
cd ~/ns-allinone-3.40-qsaqmaodv/ns-3.40
./ns3 build 2>&1 | tail -10
```

---

### Bug 2: `fanet-sim.cc` trong repo bị truncate ở dòng ~420

**Triệu chứng:** Build fail với lỗi unmatched `{` tại line 420 (code kết thúc giữa OnOffHelper).

**Nguyên nhân:** File `src/fanet-sim.cc` trong repo chỉ có 420 dòng, thiếu toàn bộ phần traffic setup + FlowMonitor + metrics + CSV writing + `return 0`.

**Cách phát hiện:**
```bash
wc -l ~/qsaqmaodv-ns3/src/fanet-sim.cc  # → 420 (lẽ ra phải ~580+)
tail -5 ~/qsaqmaodv-ns3/src/fanet-sim.cc # → kết thúc giữa chừng với "On"
```

**Fix:** Chạy `python3 src/fix-fanet-sim.py` để append phần code còn thiếu (dựa trên `hsaqmaodv-ns3/src/fanet-sim.cc` làm reference). Script tự động:
1. Tìm điểm cắt (`ApplicationContainer clientApps;`)
2. Append OnOff setup + FlowMonitor + metrics + CSV + `return 0`
3. Copy sang `~/qsaqmaodv-ns3/src/fanet-sim.cc`

**Lưu ý:** Sau khi fix, push lên GitHub:
```bash
cd ~/qsaqmaodv-ns3
git add src/fanet-sim.cc
git commit -m "fix: complete fanet-sim.cc"
git push
```

---

### Bug 3: `--qs*` flags bị cắt khi truyền qua xargs (rc=1 từ script)

**Triệu chứng:** QSAQMAODV fail rc=1 khi chạy qua script nhưng chạy tay thì OK.

**Nguyên nhân:** Biến `BASE_FLAGS`, `QS_FLAGS` được định nghĩa với `\` + newline (line continuation trong bash). Khi `printf '%s'` ghi ra job file, newline được giữ nguyên → `xargs -L 1` đọc từng dòng → args bị cắt → flag trở thành `--q` hoặc rỗng → ns-3 reject.

**Ví dụ sai:**
```bash
BASE_FLAGS="--mobility=GAUSS \
            --numNodes=15"   # ← có newline trong string!
```

**Fix (v3):** Viết tất cả flag strings trên **1 dòng duy nhất**:
```bash
BASE_FLAGS="--mobility=GAUSS --enableEnergy=1 --alpha=0.85 --numNodes=15 ..."
QS_FLAGS_DEFAULT="--qsAlpha0=0.5 --qsGamma=0.9 ..."
```

**Quy tắc:** Bất kỳ biến nào được ghi vào job file qua `echo`/`printf` rồi đọc bởi `xargs -L 1` **phải là chuỗi 1 dòng tuyệt đối**.

---

### Bug 4: VM hết RAM khi chạy JOBS=6 với N≥75

**Triệu chứng:** CPU 97.6% IO wait, load average 33, free RAM < 300MB, script chậm như đứng.

**Nguyên nhân:** Mỗi ns-3 process với N=75-100 nodes dùng ~5GB RAM. JOBS=6 → 6×5GB = 30GB, gần hết toàn bộ RAM 32GB. Kernel thrash.

**Fix:**
```bash
ulimit -c 0   # Tắt core dump
JOBS=3        # Giảm xuống 3 (3×5GB = 15GB, an toàn cho 32GB RAM)
```

**Quy tắc:** `JOBS ≤ floor(RAM_GB / ram_per_job_GB)`. Với N≥50, mỗi job cần ~5GB → JOBS≤6 cho 32GB RAM, nhưng an toàn nhất là JOBS=3.

---

### Bug 5: `git pull` conflict khi có local changes

**Triệu chứng:** `git pull` abort với "local changes would be overwritten".

**Fix:**
```bash
git checkout <file-bị-conflict>
git pull
```

Hoặc nếu muốn giữ local changes:
```bash
git stash
git pull
git stash pop
```

---

### Bug 6: `unused variable 'startBase'` → build error

**Triệu chứng:** ns-3 build với `-Werror` biến warning thành error.

**Nguyên nhân:** `fanet-sim.cc` bị truncate → `startBase` khai báo nhưng code dùng nó (OnOff loop) bị cắt mất → compiler báo unused.

**Fix:** Chạy `fix-fanet-sim.py` để hoàn thiện file (không cần xoá `startBase` vì code đầy đủ sẽ dùng nó).

---

## 6. Lưu ý vận hành

### Thời gian ước tính
| Họ | Thời gian (JOBS=3) |
|----|--------------------|
| N (5–30) | ~1–2 giờ |
| N (40–100) | ~10–20 giờ |
| S, L, E | ~2–4 giờ mỗi họ |
| W, M | ~2–5 giờ mỗi họ |
| STAT, ELONG | ~1 giờ mỗi cái |
| **Tổng** | **~24–36 giờ** |

### Luôn dùng tmux
```bash
tmux new -s <tên>        # Tạo session
tmux attach -t <tên>     # Quay lại
# Ctrl+B D               # Detach (không kill)
```

### rc=139 là bình thường
ns-3.40 segfault sau khi simulation xong (cleanup destructor). Data đã ghi vào CSV trước đó. Script xử lý đúng: `RC=139 → OK`.

### Không dùng JOBS > RAM/5GB
Với 32GB RAM: JOBS tối đa = 6. Nhưng để an toàn khi chạy N≥50: JOBS=2–3.

**Bảng JOBS an toàn theo RAM:**

| RAM VM | N nhỏ (≤30) | N lớn (≥50) |
|--------|------------|------------|
| 16 GB | JOBS=2 | JOBS=1 |
| 32 GB | JOBS=4 | JOBS=2 |
| 64 GB | JOBS=8 | JOBS=4 |

### Sau khi xong — verify data
```bash
RDIR=$(ls -dt ~/results-paper-full-* | head -1)
for csv in $RDIR/*.csv; do
    echo "$(wc -l < $csv) rows — $(basename $csv)"
done
grep "^FAIL" $RDIR/run_full.log | sed 's/_s[0-9]*//' | sort | uniq -c | sort -rn
```

---

## 7. Sự cố VM và cách xử lý

### Bug 7: VM freeze / OOM — CPU về 0%, không SSH được

**Triệu chứng:**
- CPU utilization đột ngột về 0% trên GCP Observability dashboard
- Không thể SSH vào VM
- Trước đó: `top` hiện `97.6% wa (IO wait)`, load average > 30, free RAM < 300MB

**Nguyên nhân:** OOM (Out of Memory). Nhiều ns-3 process chạy song song với N lớn (75–100 nodes) mỗi cái ngốn ~5GB RAM. Với JOBS=6 → 30GB RAM, cộng overhead hệ thống vượt quá 32GB. Kernel OOM killer terminate hết processes, VM freeze.

**Dấu hiệu cảnh báo sớm (quan sát trên `top`):**
```
%Cpu: 0.0 us, 1.9 sy, 97.6 wa   ← IO wait cao bất thường
MiB Mem: 32093 total, 239.9 free ← RAM gần cạn
Load average: 33.13              ← Quá cao so với số cores
```

**Cách xử lý khi VM freeze:**
1. Vào **GCP Console** → chọn VM → nhấn **Reset** (hard reboot)
2. Chờ VM boot lại (~1–2 phút)
3. SSH vào, kiểm tra checkpoint và resume

**Phòng ngừa — thêm Swap (chạy 1 lần sau khi reset):**
```bash
# Tạo 16GB swap file
sudo fallocate -l 16G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Tự động mount khi reboot
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstac

# Verify
free -h   # phải thấy Swap: 16.0G
```

> Swap không nhanh bằng RAM nhưng ngăn kernel OOM kill. Với swap 16GB + RAM 32GB → tổng 48GB buffer, đủ cho JOBS=6 ngay cả với N=100.

**Resume sau khi reset VM:**
```bash
cd ~/qsaqmaodv-ns3

# Kiểm tra bao nhiêu run đã xong
RDIR=$(ls -dt ~/results-paper-full-* | head -1)
echo "Đã xong: $(grep -c '^OK' $RDIR/run_full.log 2>/dev/null || echo 0) runs"
wc -l $RDIR/*.csv 2>/dev/null

# Resume với JOBS=2 (an toàn nhất)
ulimit -c 0
tmux new -s paper-resume
RESUME=1 JOBS=2 bash scripts/run/run-paper-full.sh
```

> Script đọc `done.txt` checkpoint → tự bỏ qua các run đã xong → tiếp tục từ chỗ dừng.

---

## 8. Checklist trước khi chạy thí nghiệm

- [ ] **Swap đã tạo:** `free -h | grep Swap` → phải có ≥ 8GB
- [ ] Binary nhận `--qs*` flags: `$EXEC --protocol=QSAQMAODV --qsAlpha0=0.5 --numNodes=5 --simTime=5 --seed=1 --csvFile=/tmp/t.csv 2>&1 | tail -2` → rc=0 hoặc rc=139
- [ ] `fanet-sim.cc` đầy đủ: `wc -l ~/ns-allinone-3.40-qsaqmaodv/ns-3.40/scratch/fanet-sim.cc` → phải ≥ 550
- [ ] RAM đủ: `free -h` → available ≥ JOBS×5GB
- [ ] Core dump tắt: `ulimit -c 0`
- [ ] tmux active: `tmux new -s <name>`
- [ ] Script v3: `grep "v3" scripts/run/run-paper-full.sh | head -1`

---

## 9. Cấu trúc kết quả

```
~/results-paper-full-<YYYYMMDD-HHMMSS>/
├── run_full.log          # Log toàn bộ (OK/FAIL mỗi run)
├── done.txt              # Checkpoint để RESUME
├── jobs_N.txt            # Job list Family N
├── jobs_S.txt            # ... và các họ khác
├── family_N_nodes.csv    # Dữ liệu Family N
├── family_S_speed.csv
├── family_L_load.csv
├── family_E_energy.csv
├── family_W_weight.csv
├── family_M_mixed.csv
├── stat_baseline.csv
└── elong_depletion.csv
```

**CSV columns:**
```
scenario, protocol, mobility, maxPaths, numNodes, numFlows,
meanVelMin, meanVelMax, pktInterval, simTime, seed,
deliveryRatio, avgDelayMs, throughputMbps, routingOverhead,
totalEnergyJ, nodesDead
```
